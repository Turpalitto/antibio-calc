import logging
import re
from pathlib import Path
from typing import Any

from config import ANTIBIOTIC_NAMES
from section_detector import detect_sections

logger = logging.getLogger(__name__)

_DURATION_RE = re.compile(
    r"(?:в течение|курс\s*|на\s*|продолжительность\s*)\s*\d+(?:\s*[-–]\s*\d+)?\s*(?:дн|дней|сут|суток|нед|недели)",
    re.IGNORECASE,
)
_DRUG_NAMES_LOWER = [d.lower() for d in ANTIBIOTIC_NAMES]


def compute_confidence_score(
    drug_count: int,
    has_treatment_section: bool,
    has_dosing: bool,
    has_duration: bool,
    keyword_count: int,
) -> int:
    score = 0
    score += min(drug_count * 10, 40)
    if has_treatment_section:
        score += 20
    if has_dosing:
        score += 20
    if has_duration:
        score += 10
    score += min(keyword_count * 2, 10)
    return min(score, 100)


def _count_drugs_in_text(text: str) -> tuple[int, list[str]]:
    text_lower = text.lower()
    found = []
    for drug_lower, drug_orig in zip(_DRUG_NAMES_LOWER, ANTIBIOTIC_NAMES):
        if drug_lower in text_lower:
            found.append(drug_orig)
    return len(found), found


def _has_dosing(text: str) -> bool:
    return bool(re.search(r"\d+\s*(?:мг|г|мг/кг|МЕ|мл)\b", text, re.IGNORECASE))


def _has_duration(text: str) -> bool:
    return bool(_DURATION_RE.search(text))


def classify_one(item: dict[str, Any]) -> dict[str, Any]:
    pdf_path_str = item.get("pdf_path", "")
    if not pdf_path_str or not Path(pdf_path_str).exists():
        return {
            **item,
            "abx_level": "D",
            "confidence_score": 0,
            "matched_drugs": [],
            "matched_sections": [],
            "matched_pages": [],
            "has_dosing_info": False,
            "has_duration_info": False,
            "extraction_priority": "skip",
        }

    pdf_path = Path(pdf_path_str)
    section_data = detect_sections(pdf_path, clinrec_id=item.get("Id", 0))
    relevant_text = section_data.get("relevant_text", "")

    drug_count, matched_drugs = _count_drugs_in_text(relevant_text)
    matched_sections = [s["section"] for s in section_data.get("sections_found", [])]
    matched_pages = section_data.get("relevant_pages", [])

    has_treatment = len(matched_sections) > 0
    has_dosing = _has_dosing(relevant_text)
    has_duration = _has_duration(relevant_text)

    keyword_count = len(item.get("abx_keywords_found", []))
    score = compute_confidence_score(
        drug_count=drug_count,
        has_treatment_section=has_treatment,
        has_dosing=has_dosing,
        has_duration=has_duration,
        keyword_count=keyword_count,
    )

    if drug_count >= 3 and has_treatment and has_dosing and has_duration and score >= 80:
        level = "A"
        priority = "high"
    elif drug_count >= 1 and has_treatment and score >= 50:
        level = "B"
        priority = "medium"
    elif drug_count == 0 and not has_dosing and keyword_count == 0:
        level = "D"
        priority = "skip"
        score = 0
    elif score >= 1:
        level = "C"
        priority = "low"
    else:
        level = "D"
        priority = "skip"
        score = 0

    return {
        **item,
        "abx_level": level,
        "confidence_score": score,
        "matched_drugs": matched_drugs,
        "matched_sections": matched_sections,
        "matched_pages": matched_pages,
        "has_dosing_info": has_dosing,
        "has_duration_info": has_duration,
        "extraction_priority": priority,
    }
