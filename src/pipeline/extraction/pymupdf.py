"""PyMuPDF extractor. Primary, fast."""

from pathlib import Path
from typing import List
import time

from .base import DocumentExtractor, Document, Page


class PyMuPDFExtractor(DocumentExtractor):
    """Wraps current fitz logic."""

    @property
    def name(self) -> str:
        return "pymupdf"

    def extract(self, pdf_path: Path) -> Document:
        t0 = time.time()
        import fitz

        doc = fitz.open(str(pdf_path))
        pages: List[Page] = []
        low_text = 0

        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            if len(text.strip()) < 80:
                low_text += 1
            pages.append(Page(page_num=i, text=text))

        full_text = "\n".join(p.text for p in pages)
        doc.close()

        from .quality import assess_pymupdf_quality
        conf, _ = assess_pymupdf_quality(full_text, len(pages))

        elapsed = (time.time() - t0) * 1000
        return Document(
            source="pymupdf",
            pdf_path=pdf_path,
            pages=pages,
            full_text=full_text,
            confidence=conf,
            markdown="",  # pymupdf is text only
            elapsed_time_ms=elapsed,
        )
