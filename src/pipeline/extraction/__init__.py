"""Document-extraction package: public re-exports (explicit `__all__`)."""

from .base import Document, Page, DocumentExtractor
from .router import ExtractorRouter
from .pymupdf import PyMuPDFExtractor
from .mineru import MinerUExtractor
from .docling import DoclingExtractor  # P4.1
from .quality import assess_pymupdf_quality
from .config import ExtractionConfig, get_config

__all__ = [
    "Document",
    "Page",
    "DocumentExtractor",
    "ExtractorRouter",
    "PyMuPDFExtractor",
    "MinerUExtractor",
    "DoclingExtractor",
    "assess_pymupdf_quality",
    "ExtractionConfig",
    "get_config",
]
