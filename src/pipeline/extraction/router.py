"""Router decides primary vs fallbacks based on quality. Extensible. Per-page fallback support."""

import logging
import time
from pathlib import Path
from typing import Optional, List
import tempfile
import shutil

from .base import Document, Page
from .pymupdf import PyMuPDFExtractor
from .mineru import MinerUExtractor
from .quality import assess_pymupdf_quality, assess_page_quality
from .config import get_config
from .cache import get_cache
from .metrics import get_metrics
from .layout import add_layout_to_document  # P4.2
from .semantic import add_semantic_to_document  # P4.3

logger = logging.getLogger(__name__)

# Registry - add new OCR here, no change to router logic.
_EXTRACTOR_REGISTRY = {
    "pymupdf": PyMuPDFExtractor,
    "mineru": MinerUExtractor,
    "docling": "docling",  # lazy marker for P4.1
}

def _get_docling():
    from .docling import DoclingExtractor
    return DoclingExtractor


def get_extractor(name: str):
    if name == "docling" or _EXTRACTOR_REGISTRY.get(name) == "docling":
        from .docling import DoclingExtractor
        return DoclingExtractor()
    cls = _EXTRACTOR_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown extractor: {name}")
    return cls()


class ExtractorRouter:
    """Config driven. Per-page fallback. Multiple fallbacks. Provenance + metrics ready."""

    # M-38: `add_layout_to_document` was called TWICE on the happy path (once right
    # after primary extraction, once again before the semantic layer).  The second
    # run re-did the whole layout pipeline and APPENDED duplicate tables to
    # `doc.tables` / `doc.structured_tables`.  The shared layout processor is also
    # now cached, so the models load once per process (M-29).
    def __init__(self, primary: Optional = None, fallbacks: Optional[List] = None):
        cfg = get_config()
        self.primary = primary or get_extractor(cfg.primary)
        if fallbacks is None:
            self.fallbacks = [get_extractor(name) for name in cfg.fallbacks]
        else:
            self.fallbacks = fallbacks
        self.fallback = self.fallbacks[0] if self.fallbacks else None
        self._last_source = None
        self.cfg = cfg

    def _apply_layout(self, doc: Document, pdf_path: Path) -> None:
        """Run layout at most once per document, and only if not already applied."""
        if doc.metadata.get("layout_processed"):
            return
        try:
            add_layout_to_document(doc, pdf_path)
        except Exception as e:
            doc.metadata["layout_error"] = str(e)
            doc.metadata["layout_processed"] = False

    def _apply_semantic(self, doc: Document, engine: str) -> None:
        if doc.metadata.get("semantic_processed"):
            return
        try:
            add_semantic_to_document(doc, engine or "unknown")
        except Exception as e:
            doc.metadata["semantic_error"] = str(e)
            doc.metadata["semantic_processed"] = False

    def extract(self, pdf_path: Path) -> Document:
        t0 = time.time()
        metrics = get_metrics()
        used_cache = False

        # Transparent cache check
        cache = get_cache()
        cached = cache.get(pdf_path)
        if cached:
            logger.info(f"Cache hit for {pdf_path.name}")
            self._last_source = cached.source + "+cache"
            used_cache = True
            elapsed = time.time() - t0
            metrics.record_document(cached, elapsed, used_cache=True)
            self._apply_layout(cached, pdf_path)
            self._apply_semantic(cached, self._last_source or "unknown")
            return cached

        logger.info(f"Using {self.primary.name}")
        primary_doc = self.primary.extract(pdf_path)

        # P4.2 Layout after extraction
        self._apply_layout(primary_doc, pdf_path)


        # Per page quality assessment
        page_provenance = []
        bad_indices = []
        thresh = getattr(self.cfg, 'quality_threshold', 0.65)
        bad_thresh = getattr(self.cfg, 'bad_page_text_threshold', 50)

        for i, p in enumerate(primary_doc.pages):
            sc, rs = assess_page_quality(p.text)
            is_bad = (sc < thresh) or ("very_short" in rs) or ("empty" in rs) or len(p.text.strip()) < bad_thresh
            prov = {
                "page": p.page_num,
                "source": "pymupdf",
                "quality": round(sc, 3),
                "fallback_reason": ",".join(rs) if is_bad else None,
                "ocr_time": 0.0,
            }
            page_provenance.append(prov)
            if is_bad:
                bad_indices.append(i)

        if not bad_indices or not getattr(self.cfg, 'per_page_fallback', True):
            # whole doc decision (old path or all good)
            score, reasons = assess_pymupdf_quality(primary_doc.full_text, len(primary_doc.pages))
            if score >= thresh and not bad_indices:
                primary_doc.confidence = score
                primary_doc.metadata["page_provenance"] = page_provenance
                self._last_source = self.primary.name
                logger.info(f"Returning unified document from {self._last_source}")
                cache.put(pdf_path, primary_doc)
                elapsed = time.time() - t0
                metrics.record_document(primary_doc, elapsed)
                # M-38: layout was already applied above; running it again here
                # appended duplicate tables.  The guards are no-ops now.
                self._apply_layout(primary_doc, pdf_path)
                self._apply_semantic(primary_doc, self._last_source or "pymupdf")
                return primary_doc
            # fall to fallback below

        logger.info(f"Per-page: {len(bad_indices)} bad pages detected")

        # Selective OCR for bad pages only
        try:
            ocr_replacements = self._ocr_selected_pages(pdf_path, [primary_doc.pages[i] for i in bad_indices])
            final_pages = list(primary_doc.pages)
            full_texts = []
            for idx, bad_idx in enumerate(bad_indices):
                orig_page = primary_doc.pages[bad_idx]
                ocr_page = ocr_replacements[idx]
                orig_text = (orig_page.text or "").strip()
                new_text = (getattr(ocr_page, 'text', '') or "").strip()
                # only replace if OCR clearly better (prevents degrading good pymupdf text for semantic)
                use_ocr = len(new_text) > max(80, len(orig_text) + 20) \
                    and not getattr(ocr_page, "ocr_failed", False)
                text_to_use = new_text if use_ocr else orig_text
                final_pages[bad_idx] = Page(page_num=orig_page.page_num, text=text_to_use, tables=orig_page.tables or [])
                page_provenance[bad_idx]["source"] = (
                    (ocr_page.source if hasattr(ocr_page, 'source') else "mineru")
                    if use_ocr else "pymupdf"
                )
                page_provenance[bad_idx]["ocr_time"] = getattr(ocr_page, 'ocr_time', 0.0) if use_ocr else 0.0
                if getattr(ocr_page, "ocr_failed", False):
                    # M-42: record the failure instead of presenting it as an OCR result
                    page_provenance[bad_idx]["fallback_failed"] = "all_ocr_engines_failed"
                full_texts.append(final_pages[bad_idx].text)

            # rebuild full_text
            full_text = "\n".join(p.text for p in final_pages)
            # M-40: the label was decided by whether the bad-page COUNT was smaller
            # than the total, not by whether any page was actually replaced.  Count
            # the real replacements.
            replaced = sum(
                1 for prov in page_provenance
                if prov.get("source", "pymupdf") not in ("pymupdf", "", None)
            )
            if replaced == 0:
                source_name = "pymupdf"
            elif replaced == len(final_pages):
                source_name = self.fallbacks[0].name if self.fallbacks else "mineru"
            else:
                source_name = "mixed"
            doc = Document(
                source=source_name,
                pdf_path=pdf_path,
                pages=final_pages,
                full_text=full_text,
                metadata={"page_provenance": page_provenance, "per_page_fallback": True},
                confidence=sum(p["quality"] for p in page_provenance) / len(page_provenance),
            )
            self._last_source = doc.source
            logger.info(f"Returning per-page unified document from {self._last_source}")
            cache.put(pdf_path, doc)
            elapsed = time.time() - t0
            metrics.record_document(doc, elapsed)
            self._apply_layout(doc, pdf_path)
            self._apply_semantic(doc, self._last_source or "mixed")
            return doc
        except Exception as e:
            logger.error(f"Per-page fallback failed: {e}. Falling back to full document fallback.")
            # fallthrough to full fallback

        # Full fallback (original behavior)
        for fb in self.fallbacks:
            logger.info(f"Fallback -> {fb.name}")
            try:
                fb_doc = fb.extract(pdf_path)
                fb_doc.confidence = min(fb_doc.confidence or 0.8, 0.9)
                # attach provenance for all as fallback
                for prov in page_provenance:
                    prov["source"] = fb.name
                fb_doc.metadata["page_provenance"] = page_provenance
                self._last_source = fb.name
                logger.info(f"{fb.name} completed. Returning unified document from {self._last_source}")
                cache.put(pdf_path, fb_doc)
                elapsed = time.time() - t0
                metrics.record_document(fb_doc, elapsed)
                self._apply_layout(fb_doc, pdf_path)
                self._apply_semantic(fb_doc, fb.name)
                return fb_doc
            except Exception as e:
                logger.error(f"{fb.name} failed: {e}")
                continue

        # M-41: this returned the primary document at confidence 0.3 with a
        # `fallback_error` but WITHOUT attempting layout, so the caller received a
        # document that had never been through the table pipeline -- and the failure
        # was easy to mistake for a low-quality-but-usable result.  Layout is now
        # attempted, and the unusable outcome is recorded explicitly.
        primary_doc.metadata["fallback_error"] = "all fallbacks failed"
        primary_doc.metadata["extraction_unusable"] = True
        primary_doc.metadata["page_provenance"] = page_provenance
        primary_doc.confidence = 0.3
        self._last_source = self.primary.name + "+failed"
        self._apply_layout(primary_doc, pdf_path)
        self._apply_semantic(primary_doc, self._last_source)
        return primary_doc

    def _ocr_selected_pages(self, pdf_path: Path, bad_pages: List[Page]) -> List[Page]:
        """Run OCR only on bad pages using temp single-page PDFs.

        M-43: the source PDF was re-opened PER BAD PAGE; it is now opened ONCE and
        sliced from the shared handle.

        M-42: on total OCR failure the original PyMuPDF text used to be substituted
        and the page was recorded as a successful ``mineru`` replacement.  The
        failure is now flagged on the page so the caller can refuse the swap and the
        provenance says what actually happened.
        """
        import fitz

        results: List[Page] = []
        src = fitz.open(str(pdf_path))
        try:
            for page in bad_pages:
                t0 = time.time()
                ocr_failed = False
                with tempfile.TemporaryDirectory() as tmp:
                    # create a 1-page pdf containing only this page
                    single = fitz.open()
                    single.insert_pdf(src, from_page=page.page_num, to_page=page.page_num)
                    single_pdf = Path(tmp) / "bad_page.pdf"
                    single.save(str(single_pdf))
                    single.close()

                    # run the first available fallback on the single-page pdf
                    ocr_text = ""
                    for fb in self.fallbacks:
                        try:
                            fb_doc = fb.extract(single_pdf)
                            ocr_text = fb_doc.full_text
                            break
                        except Exception:
                            continue
                    if not ocr_text:
                        # keep the original text, but say so
                        ocr_text = page.text
                        ocr_failed = True
                dt = round(time.time() - t0, 3)
                new_page = Page(page_num=page.page_num, text=ocr_text)
                setattr(new_page, "source", "ocr_failed" if ocr_failed else "mineru")
                setattr(new_page, "ocr_time", dt)
                setattr(new_page, "ocr_failed", ocr_failed)
                results.append(new_page)
        finally:
            src.close()
        return results
