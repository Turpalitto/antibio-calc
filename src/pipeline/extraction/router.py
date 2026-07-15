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
            try:
                if not cached.metadata.get("layout_processed"):
                    add_layout_to_document(cached, pdf_path)
            except Exception as e:
                cached.metadata["layout_error"] = str(e)
            try:
                if not cached.metadata.get("semantic_processed"):
                    add_semantic_to_document(cached, self._last_source or "unknown")
            except Exception as e:
                cached.metadata["semantic_error"] = str(e)
                cached.metadata["semantic_processed"] = False
            return cached

        logger.info(f"Using {self.primary.name}")
        primary_doc = self.primary.extract(pdf_path)

        # P4.2 Layout after extraction
        try:
            add_layout_to_document(primary_doc, pdf_path)
        except Exception as e:
            primary_doc.metadata["layout_error"] = str(e)

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
                try:
                    add_layout_to_document(primary_doc, pdf_path)
                except Exception as e:
                    primary_doc.metadata["layout_error"] = str(e)
                try:
                    add_semantic_to_document(primary_doc, self._last_source or "pymupdf")
                except Exception as e:
                    primary_doc.metadata["semantic_error"] = str(e)
                    primary_doc.metadata["semantic_processed"] = False
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
                use_ocr = len(new_text) > max(80, len(orig_text) + 20)
                text_to_use = new_text if use_ocr else orig_text
                final_pages[bad_idx] = Page(page_num=orig_page.page_num, text=text_to_use, tables=orig_page.tables or [])
                page_provenance[bad_idx]["source"] = (ocr_page.source if hasattr(ocr_page, 'source') else "mineru") if use_ocr else "pymupdf"
                page_provenance[bad_idx]["ocr_time"] = getattr(ocr_page, 'ocr_time', 0.0) if use_ocr else 0.0
                full_texts.append(final_pages[bad_idx].text)

            # rebuild full_text
            full_text = "\n".join(p.text for p in final_pages)
            doc = Document(
                source="mixed" if len(bad_indices) < len(final_pages) else (self.fallbacks[0].name if self.fallbacks else "mineru"),
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
            try:
                add_layout_to_document(doc, pdf_path)
            except Exception as e:
                doc.metadata["layout_error"] = str(e)
            try:
                add_semantic_to_document(doc, self._last_source or "mixed")
            except Exception as e:
                doc.metadata["semantic_error"] = str(e)
                doc.metadata["semantic_processed"] = False
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
                try:
                    add_layout_to_document(fb_doc, pdf_path)
                except Exception as e:
                    fb_doc.metadata["layout_error"] = str(e)
                try:
                    add_semantic_to_document(fb_doc, fb.name)
                except Exception as e:
                    fb_doc.metadata["semantic_error"] = str(e)
                    fb_doc.metadata["semantic_processed"] = False
                return fb_doc
            except Exception as e:
                logger.error(f"{fb.name} failed: {e}")
                continue

        primary_doc.metadata["fallback_error"] = "all fallbacks failed"
        primary_doc.metadata["page_provenance"] = page_provenance
        primary_doc.confidence = 0.3
        self._last_source = self.primary.name + "+failed"
        try:
            add_semantic_to_document(primary_doc, self._last_source)
        except Exception as e:
            primary_doc.metadata["semantic_error"] = str(e)
            primary_doc.metadata["semantic_processed"] = False
        return primary_doc

    def _ocr_selected_pages(self, pdf_path: Path, bad_pages: List[Page]) -> List[Page]:
        """Run OCR only on bad pages using temp single-page PDFs. Returns list of Page with OCR text."""
        import fitz
        results = []
        for p in bad_pages:
            t0 = time.time()
            with tempfile.TemporaryDirectory() as tmp:
                # create 1-page pdf with only this page
                src = fitz.open(str(pdf_path))
                dst = fitz.open()
                dst.insert_pdf(src, from_page=p.page_num, to_page=p.page_num)
                single_pdf = Path(tmp) / "bad_page.pdf"
                dst.save(str(single_pdf))
                dst.close()
                src.close()

                # run first available fallback on the single page pdf
                ocr_text = ""
                for fb in self.fallbacks:
                    try:
                        fb_doc = fb.extract(single_pdf)
                        ocr_text = fb_doc.full_text
                        break
                    except Exception:
                        continue
                if not ocr_text:
                    ocr_text = p.text  # keep original if all failed
            dt = round(time.time() - t0, 3)
            new_page = Page(page_num=p.page_num, text=ocr_text)
            # attach temp for provenance
            setattr(new_page, 'source', 'mineru')
            setattr(new_page, 'ocr_time', dt)
            results.append(new_page)
        return results
