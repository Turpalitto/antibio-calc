"""Quality checker for PyMuPDF output. Deterministic rules."""

import re
from typing import Tuple


def assess_pymupdf_quality(text: str, num_pages: int) -> Tuple[float, list[str]]:
    """Return (score 0-1, reasons)."""
    if not text or num_pages == 0:
        return 0.0, ["empty"]

    reasons = []
    score = 1.0

    clean = text.strip()
    char_count = len(clean)

    if char_count < 200:
        score *= 0.3
        reasons.append("very_short")

    cyrillic = len(re.findall(r"[а-яА-ЯёЁ]", clean))
    cyrillic_ratio = cyrillic / max(char_count, 1)
    if cyrillic_ratio < 0.1:
        score *= 0.6
        reasons.append("low_cyrillic")

    # replacement chars
    if "\ufffd" in clean or "�" in clean:
        score *= 0.5
        reasons.append("replacement_chars")

    # avg line length
    lines = [l for l in clean.splitlines() if l.strip()]
    if lines:
        avg_len = sum(len(l) for l in lines) / len(lines)
        if avg_len < 15:
            score *= 0.7
            reasons.append("short_lines")

    # empty pages heuristic (caller can pass low_text_count)
    if num_pages > 0:
        # caller will adjust
        pass

    score = max(0.0, min(1.0, score))
    return score, reasons or ["ok"]


def assess_page_quality(text: str) -> tuple[float, list[str]]:
    """Quality for single page."""
    return assess_pymupdf_quality(text, 1)
