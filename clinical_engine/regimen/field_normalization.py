"""Safe, source-backed field normalization (P5.4 Task 4).

Design authority: DOSE_NORMALIZATION_POLICY.md, RC024_DOSE_AUDIT_REPORT.md.

Rules (hard):
- Never generate a value. Every output is recovered from literal characters in the
  regimen's OWN source_quote — never inferred from population/class/similar-regimen
  statistics.
- A route is only recovered when EXACTLY ONE route family matches (ambiguous "или"
  branches, per RC024 Category C, are left unset — never guessed).
- normalized_regimens.sqlite is NEVER written; this operates purely on ClinicalRegimen
  construction inside the assembly layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from clinical_engine.regimen.clinical_regimen import UNKNOWN, FieldProvenance

# Canonical route families. Patterns are deliberately specific (no bare "в"/"м") to avoid
# false-positive matches. Each family is checked independently; a route is recovered ONLY
# if exactly one family matches the source_quote.
_ROUTE_PATTERNS: dict[str, re.Pattern] = {
    "intravenous": re.compile(r"внутривенн\w*|в/в\b", re.IGNORECASE),
    "oral": re.compile(r"перорал\w*|внутрь\b|per\s*os", re.IGNORECASE),
    "intramuscular": re.compile(r"внутримышечн\w*|в/м\b", re.IGNORECASE),
    "topical": re.compile(r"\bместно\b|наружн\w*", re.IGNORECASE),
    "rectal": re.compile(r"ректальн\w*", re.IGNORECASE),
    "ophthalmic": re.compile(r"глазн\w*", re.IGNORECASE),
    "subcutaneous": re.compile(r"подкожн\w*|п/к\b", re.IGNORECASE),
    "inhalation": re.compile(r"ингаляционн\w*", re.IGNORECASE),
}

_UNIT_CANON = {
    "г": "g", "мг": "mg", "мкг": "mcg", "мл": "ml", "ед": "IU",
    "g": "g", "mg": "mg", "mcg": "mcg", "ml": "ml", "iu": "IU",
    "мг/кг": "mg/kg", "mg/kg": "mg/kg",
}


@dataclass
class NormalizationOutcome:
    field: str
    recovered: bool
    value: str = ""
    reason: str = ""            # why recovered / why NOT recovered (ambiguous, no match)
    provenance: FieldProvenance | None = None


@dataclass
class NormalizationRunMetrics:
    examined: int = 0
    route_recovered: int = 0
    route_ambiguous_skipped: int = 0
    route_no_match_skipped: int = 0
    unit_canonicalized: int = 0

    def as_dict(self) -> dict:
        return {
            "examined": self.examined,
            "route_recovered": self.route_recovered,
            "route_ambiguous_skipped": self.route_ambiguous_skipped,
            "route_no_match_skipped": self.route_no_match_skipped,
            "unit_canonicalized": self.unit_canonicalized,
        }


def recover_route_from_quote(source_quote: str, regimen_id: str, source_pdf: str,
                             source_page: str) -> NormalizationOutcome:
    """Recover `route` ONLY if exactly one route family matches the literal source text."""
    q = source_quote or ""
    matched = [name for name, pat in _ROUTE_PATTERNS.items() if pat.search(q)]
    if len(matched) == 0:
        return NormalizationOutcome(field="route", recovered=False,
                                    reason="no_route_keyword_in_source_quote")
    if len(matched) > 1:
        return NormalizationOutcome(field="route", recovered=False,
                                    reason=f"ambiguous_multiple_routes:{matched}")
    route = matched[0]
    prov = FieldProvenance(
        source_object_id=regimen_id, source_document=source_pdf,
        source_location=f"page {source_page} (route recovered from source_quote text)",
        source_store="normalized_regimens+text_normalization", scope="regimen",
    )
    return NormalizationOutcome(field="route", recovered=True, value=route,
                                reason="single_unambiguous_route_keyword_in_source_quote",
                                provenance=prov)


def canonicalize_unit(unit: str) -> str:
    """Cosmetic unit-string canonicalization. Never changes the numeric dose value."""
    if not unit:
        return unit
    key = unit.strip().lower()
    return _UNIT_CANON.get(key, unit)


def normalize_frequency_display(frequency: float | None) -> str:
    """Human-readable period label for an already-extracted frequency float.
    Does NOT alter the underlying number — display/formatting only."""
    if frequency is None:
        return UNKNOWN
    if frequency <= 0:
        return UNKNOWN
    if frequency >= 1:
        # times per day
        n = round(frequency)
        return f"{n}x/day" if abs(frequency - n) < 1e-6 else f"{frequency:.2f}x/day"
    # sub-daily: represent as "once every N days"
    days = round(1.0 / frequency)
    return f"1x/{days}days"
