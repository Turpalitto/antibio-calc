"""PyMuPDF extractor. Primary, fast."""

from pathlib import Path
from typing import List
import time

from .base import DocumentExtractor, Document, Page

# L-35: the codebase mixed a 0-based (``page_num=i``, PyMuPDF index) and a 1-based
# (``table_pages`` in the candidate specs, PDF page numbers) convention with no
# shared constant.  The extractor's page_num is 0-BASED and is the canonical
# internal index; anything user-facing adds +1.  Stated once, here.
PAGE_NUM_IS_ZERO_BASED = True
PDF_PAGE_DISPLAY_OFFSET = 1


def to_display_page(page_num: int) -> int:
    """0-based internal page index -> 1-based PDF page number."""
    return page_num + PDF_PAGE_DISPLAY_OFFSET


def from_display_page(page_number: int) -> int:
    """1-based PDF page number -> 0-based internal page index."""
    return page_number - PDF_PAGE_DISPLAY_OFFSET


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
        # L-34: this counter was computed and never used, so a document that was
        # 90% image pages scored exactly like a clean one.
        low_text_pages: List[int] = []

        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            if len(text.strip()) < 80:
                low_text_pages.append(i)
            pages.append(Page(page_num=i, text=text))

        full_text = "\n".join(p.text for p in pages)
        doc.close()

        from .config import get_config
        from .quality import assess_pymupdf_quality

        conf, reasons = assess_pymupdf_quality(full_text, len(pages))
        # L-43: max_empty_pages_ratio was configured but never applied, so a mostly
        # image-only PDF was reported as good extraction.
        cfg = get_config()
        low_text_ratio = (len(low_text_pages) / len(pages)) if pages else 1.0
        if low_text_ratio > getattr(cfg, "max_empty_pages_ratio", 0.3):
            conf = min(conf, 0.3)
            reasons = list(reasons) + [
                (
                    f"low_text_page_ratio={low_text_ratio:.2f} > "
                    f"max_empty_pages_ratio={getattr(cfg, 'max_empty_pages_ratio', 0.3)}"
                )
            ]

        elapsed = (time.time() - t0) * 1000
        return Document(
            source="pymupdf",
            pdf_path=pdf_path,
            pages=pages,
            full_text=full_text,
            confidence=conf,
            markdown="",  # pymupdf is text only
            elapsed_time_ms=elapsed,
            warnings=[
                f"page {to_display_page(i)}: little or no text layer"
                for i in low_text_pages
            ],
        )
