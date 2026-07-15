"""extractor.py — thin wrapper. Uses new Document Extraction layer.

Parser and rest of pipeline untouched.
"""

import logging
from pathlib import Path
from typing import Optional

from .extraction.router import ExtractorRouter

logger = logging.getLogger(__name__)

_router: Optional[ExtractorRouter] = None


def _get_router() -> ExtractorRouter:
    global _router
    if _router is None:
        _router = ExtractorRouter()
    return _router


def extract_text(pdf_path: Path) -> Optional[str]:
    """Same signature. Now uses Router + quality gate + MinerU fallback."""
    if not pdf_path.exists():
        logger.warning(f"  PDF not found: {pdf_path}")
        return None

    try:
        doc = _get_router().extract(pdf_path)
        logger.info(f"  Extraction source={doc.source} conf={doc.confidence:.2f} pages={len(doc.pages)}")
        return doc.full_text
    except Exception as exc:
        logger.error(f"  Extraction failed for {pdf_path}: {exc}")
        return None
