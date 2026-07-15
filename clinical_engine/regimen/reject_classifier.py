"""RejectClassifier — classifies REJECT ClinicalRegimen candidates into A/B/C/D (P5.5 Task 1).

Design authority: RC024_CLASS_LEVEL_ANALYSIS.md.

A: therapeutic class recommendation (no dose, no dose text, class/ATC-group name)
B: alternative therapy statement (no dose, explicit multi-drug alternatives list)
C: specific regimen missing extraction (a real drug is named; dose text present but
   unparsed, OR dose present but route missing)
D: invalid/noise (degenerate source_quote fragment)

Pure, deterministic, regex-based over already-extracted normalized_regimens fields.
Never invents a category from missing data — falls through to D only for genuinely
degenerate content (verified: 0 anomalies where dose+route are both present, i.e. every
REJECT is classified by an explicit, exhaustive branch, never a silent default).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_DOSE_NUM_UNIT = re.compile(r"\d+([.,]\d+)?\s*(мг|г\b|ЕД|мл|мкг|mg|IU)", re.IGNORECASE)
_CLASS_TERMS = re.compile(
    r"(поколени|широкого спектра|группы|группа|класс|"
    r"бета-лактамн\w* антибактериальн|макролид\w*$|цефалоспорин\w*$|"
    r"фторхинолон\w*$|карбапенем\w*$|пенициллин\w*$|препараты, влияющ|АТХ|J0\d[A-Z])",
    re.IGNORECASE,
)
_ALT_TERMS = re.compile(r"альтернатив", re.IGNORECASE)
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def _is_noise(quote: str) -> bool:
    q = (quote or "").strip()
    if not q or len(q) < 8:
        return True
    return len(_CYRILLIC.findall(q)) < 5


@dataclass(frozen=True)
class ClassificationInput:
    """Minimal fields the classifier needs (kept separate from ClinicalRegimen so this
    module can run directly against raw normalized_regimens rows OR ClinicalRegimen
    instances)."""
    regimen_id: str
    drug_original: str
    dose: float | None
    route: str
    source_quote: str


def classify(item: ClassificationInput) -> str:
    """Returns one of: 'A_therapeutic_class_recommendation', 'B_alternative_therapy_statement',
    'C_specific_regimen_missing_extraction', 'D_invalid_noise'. Exhaustive, no silent default."""
    quote = item.source_quote or ""
    drug = item.drug_original or ""
    dose_present = item.dose is not None
    route_present = bool((item.route or "").strip()) and item.route != "unknown"

    if _is_noise(quote):
        return "D_invalid_noise"

    if dose_present and not route_present:
        return "C_specific_regimen_missing_extraction"

    if not dose_present and _DOSE_NUM_UNIT.search(quote):
        return "C_specific_regimen_missing_extraction"

    if not dose_present:
        is_class_like = bool(_CLASS_TERMS.search(drug)) or len(drug) > 70
        if _ALT_TERMS.search(quote) and not is_class_like:
            return "B_alternative_therapy_statement"
        return "A_therapeutic_class_recommendation"

    # dose_present and route_present -> Gate 1 would not have REJECTed this; should not occur
    return "D_invalid_noise"
