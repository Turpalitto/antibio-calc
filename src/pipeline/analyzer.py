"""analyzer.py — анализ текста на наличие антибиотиков."""

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from config import (
    ADDITIONAL_TERMS,
    ANTIBIOTIC_KEYWORDS,
    ANTIBIOTIC_NAMES,
    DOWNLOADS_ALL,
)
from extractor import extract_text

logger = logging.getLogger(__name__)


def build_re_patterns(word_list: list[str]) -> list[tuple[str, re.Pattern]]:
    patterns: list[tuple[str, re.Pattern]] = []
    for word in word_list:
        word_nosp = word.replace("-", r"[\s\-]*")
        word_nosp = word_nosp.replace("/", r"[\s\/]*")
        pat = re.compile(rf"(?<![а-яёa-z]){word_nosp}(?![а-яёa-z])", re.IGNORECASE)
        patterns.append((word, pat))
    return patterns


_ABX_DRUG_PATTERNS = build_re_patterns(ANTIBIOTIC_NAMES)
_ABX_KEYWORD_PATTERNS = build_re_patterns(ANTIBIOTIC_KEYWORDS)
_ABX_EXTRA_PATTERNS = build_re_patterns(ADDITIONAL_TERMS)


def analyze_one(item: dict[str, Any]) -> dict[str, Any]:
    pdf_path_str = item.get("pdf_path")
    if not pdf_path_str:
        return {**item, "has_antibiotics": False, "abx_drugs_found": [], "abx_keywords_found": [], "abx_score": 0}

    pdf_path = Path(pdf_path_str)
    text = extract_text(pdf_path)

    if not text:
        return {**item, "has_antibiotics": False, "abx_drugs_found": [], "abx_keywords_found": [], "abx_score": 0}

    text_lower = text.lower()

    drugs_found: list[str] = []
    for name, pattern in _ABX_DRUG_PATTERNS:
        if pattern.search(text_lower):
            drugs_found.append(name)

    keywords_found: list[str] = []
    for kw, pattern in _ABX_KEYWORD_PATTERNS:
        if pattern.search(text_lower):
            keywords_found.append(kw)

    extra_found: list[str] = []
    for term, pattern in _ABX_EXTRA_PATTERNS:
        if pattern.search(text_lower):
            extra_found.append(term)

    # scoring: drugs are highest weight
    score = len(drugs_found) * 10 + len(keywords_found) * 5 + len(extra_found) * 2

    has_abx = score > 0

    return {
        **item,
        "has_antibiotics": has_abx,
        "abx_drugs_found": drugs_found,
        "abx_keywords_found": keywords_found,
        "abx_extra_found": extra_found,
        "abx_score": score,
    }
