"""Docling extractor. Third engine for unified parsing and normalization (P4.1)."""

from pathlib import Path
from typing import List
import time

from .base import DocumentExtractor, Document, Page


class DoclingExtractor(DocumentExtractor):
    """Docling as additional engine for structured output, layout awareness, normalization.
    Complements PyMuPDF and MinerU. Returns same Unified Document.
    """

    @property
    def name(self) -> str:
        return "docling"

    def extract(self, pdf_path: Path) -> Document:
        t0 = time.time()
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        docling_doc = result.document

        md = docling_doc.export_to_markdown() or ""
        text = docling_doc.export_to_text() or ""

        pages: List[Page] = []
        if hasattr(docling_doc, "pages") and docling_doc.pages:
            # Build per-page text from doc.texts (reliable way)
            page_text_map = {}
            if hasattr(docling_doc, "texts"):
                for item in docling_doc.texts or []:
                    for prov in getattr(item, "prov", []) or []:
                        pno = getattr(prov, "page_no", None)
                        if pno is not None:
                            if pno not in page_text_map:
                                page_text_map[pno] = []
                            page_text_map[pno].append(getattr(item, "text", "") or "")
            # pages dict keys are 1-based
            for page_no in sorted(docling_doc.pages.keys()):
                page_text = "\n".join(page_text_map.get(page_no, []))
                if not page_text:
                    # fallback to full if per-page not available
                    page_text = md or text
                pages.append(Page(page_num=page_no - 1, text=page_text))
        else:
            pages = [Page(page_num=0, text=md or text)]

        full_text = md or text

        # Collect tables, images if available
        tables = []
        if hasattr(docling_doc, "tables"):
            for t in docling_doc.tables or []:
                tables.append({"type": "table", "content": str(t)[:500]})

        images = []
        if hasattr(docling_doc, "pictures"):
            for pic in docling_doc.pictures or []:
                images.append({"type": "picture", "ref": str(pic)[:100]})

        elapsed = (time.time() - t0) * 1000

        meta = {
            "docling_version": "2.112.0",
            "origin": str(getattr(docling_doc, "origin", "")),
            "num_raw_pages": len(getattr(docling_doc, "pages", [])),
            "tables_count": len(getattr(docling_doc, "tables", []) or []),
            "pictures_count": len(getattr(docling_doc, "pictures", []) or []),
            "markdown": md,
            "raw_text": text,
        }

        return Document(
            source="docling",
            pdf_path=pdf_path,
            pages=pages,
            full_text=full_text,
            markdown=md,
            tables=tables,
            images=images,
            confidence=0.88,  # Docling generally high quality structured
            metadata=meta,
            elapsed_time_ms=elapsed,
            warnings=[],
            errors=[],
        )
