import logging
import re
from typing import Any

from config import ANTIBIOTIC_NAMES

logger = logging.getLogger(__name__)

ABX_SECTION_RE = re.compile(
    r"(?:антибактериальн\w+\s+терапи\w+|антимикробн\w+\s+терапи\w+|этиотропн\w+\s+терапи\w+|антибиотикотерапи\w+|антибиотикопрофилактик\w+)",
    re.IGNORECASE,
)

TREATMENT_TABLE_RE = re.compile(
    r"(?:лекарственн\w+\s+препарат\w+|схем\w+\s+лечени\w+|режим\w+\s+дозировани\w+|таблиц\w+\s+доз)",
    re.IGNORECASE,
)

MEDIUM_KEYWORDS = [
    "инфекция", "инфекции", "инфекционный",
    "бактериальный", "бактериальная", "бактериальное",
    "гнойный", "гнойная", "гнойное",
    "обострение", "обострении",
    "этиотропная", "этиотропной",
    "сепсис", "септический",
    "воспаление", "воспалительный",
    "микробный", "микробная",
]

ICD_ABX_PREFIXES = [
    "A", "J", "K", "N", "L",
]

_ICD_ABX_EXACT = {
    "A00", "A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09",
    "A20", "A21", "A22", "A23", "A24", "A25", "A26", "A27", "A28",
    "A30", "A31", "A32", "A33", "A34", "A35", "A36", "A37", "A38", "A39", "A40", "A41", "A46", "A48",
    "J00", "J01", "J02", "J03", "J04", "J05", "J06",
    "J13", "J14", "J15", "J16", "J17", "J18",
    "J20", "J21", "J22",
    "J32", "J36", "J37",
    "J39",
    "J85", "J86",
    "K35", "K37", "K61", "K65", "K80", "K81", "K83",
    "L01", "L02", "L03", "L04", "L05", "L08",
    "L30", "L98",
    "N10", "N11", "N12", "N13", "N15",
    "N30", "N34", "N39",
    "N70", "N71", "N72", "N73", "N75", "N76",
}

_DRUG_NAMES_LOWER = [d.lower() for d in ANTIBIOTIC_NAMES]
_MEDIUM_KEYWORDS_LOWER = [k.lower() for k in MEDIUM_KEYWORDS]


def _find_drugs(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for drug_lower, drug_orig in zip(_DRUG_NAMES_LOWER, ANTIBIOTIC_NAMES):
        if drug_lower in text_lower:
            found.append(drug_orig)
    return list(dict.fromkeys(found))


def _find_keywords(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for kw_lower, kw_orig in zip(_MEDIUM_KEYWORDS_LOWER, MEDIUM_KEYWORDS):
        if kw_lower in text_lower:
            found.append(kw_orig)
    return list(dict.fromkeys(found))


def _find_abx_sections(text: str) -> bool:
    return bool(ABX_SECTION_RE.search(text))


def _find_treatment_table(text: str) -> bool:
    return bool(TREATMENT_TABLE_RE.search(text))


def _match_icd(mkbs: list[dict]) -> list[str]:
    matched = []
    for m in (mkbs or []):
        code = (m.get("MkbCode") or "").upper().strip()
        if not code:
            continue
        prefix = code[:3]
        if prefix in _ICD_ABX_EXACT:
            matched.append(code)
    return matched


def gate_one(item: dict[str, Any], pdf_text: str = "") -> dict[str, Any]:
    name = item.get("Name", "") or ""
    code_version = item.get("CodeVersion", "") or ""
    mkbs = item.get("Mkbs") or []
    mkb_codes = [m.get("MkbCode", "") for m in mkbs if m.get("MkbCode")]

    text = pdf_text or " ".join(
        str(item.get(k, "") or "")
        for k in ("Name",)
    )
    text += " " + name

    matched_drugs = _find_drugs(text)
    matched_keywords = _find_keywords(text)
    matched_icd = _match_icd(mkbs)

    has_abx_section = _find_abx_sections(text)
    has_treatment_table = _find_treatment_table(text)

    score = 0

    if matched_drugs:
        score += min(len(matched_drugs) * 20, 50)
    if has_abx_section:
        score += 25
    if has_treatment_table:
        score += 15

    if matched_keywords:
        score += min(len(matched_keywords) * 8, 30)

    if matched_icd:
        score += min(len(matched_icd) * 10, 20)

    score = min(score, 100)

    if score >= 70:
        status = "process"
        reason = "high_confidence_antibiotics"
    elif score >= 25:
        status = "review"
        reason = "medium_confidence_keywords"
    else:
        status = "skip"
        reason = "low_confidence_no_antibiotics"

    return {
        "code_version": code_version,
        "name": name,
        "mkb": mkb_codes,
        "antibiotic_probability": score,
        "status": status,
        "matched_keywords": matched_keywords,
        "matched_drugs": matched_drugs,
        "matched_icd": matched_icd,
        "reason": reason,
    }
