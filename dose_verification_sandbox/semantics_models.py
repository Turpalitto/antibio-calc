"""Phase 2 — Canonical dose semantics model (RC-030).

Additive. Does not overload ClinicalRegimen/assembled_regimens fields and
does not mutate assembled_regimens.sqlite. See DOSE_SEMANTICS_MODEL.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

SEMANTIC_TYPES = {
    "WEIGHT_PER_DAY", "WEIGHT_PER_DOSE", "FIXED_PER_DAY", "FIXED_PER_DOSE",
    "RANGE_PER_DAY", "RANGE_PER_DOSE", "UNPARSED", "AMBIGUOUS", "MISSING", "NOT_APPLICABLE",
}

AMBIGUITY_STATUSES = {
    "UNAMBIGUOUS",
    "RESOLVED_BY_FREQUENCY_ONE",   # frequency == 1 makes per-dose vs per-day algebraically identical
    "AMBIGUOUS_NO_SIGNAL",         # no explicit textual signal found in the source window
    "AMBIGUOUS_CONFLICTING_SIGNAL",  # both per-day and per-dose signals found in the same window
    "NOT_APPLICABLE",
}


@dataclass
class DoseSemantics:
    semantics_id: str
    regimen_id: str
    regimen_version: int
    semantic_type: str
    numeric_min: Optional[float]
    numeric_max: Optional[float]
    numerator_unit: Optional[str]
    weight_denominator: bool
    time_denominator: Optional[str]     # "day" | "dose" | None
    administration_scope: Optional[str]  # free-text description of what was matched, e.g. "N раз в сутки"
    frequency: Optional[float]
    max_single_dose: Optional[float]
    max_daily_dose: Optional[float]
    source_expression: str
    normalized_expression: str
    parser_status: str                  # PARSED | UNPARSED
    ambiguity_status: str
    provenance: dict
    derived_from: str                   # "assembled_regimens.sqlite:<regimen_id>:<version>"
    confidence: float
    created_at: str
    matched_fragment: Optional[str] = None

    def __post_init__(self) -> None:
        if self.semantic_type not in SEMANTIC_TYPES:
            raise ValueError(f"invalid semantic_type: {self.semantic_type}")
        if self.ambiguity_status not in AMBIGUITY_STATUSES:
            raise ValueError(f"invalid ambiguity_status: {self.ambiguity_status}")

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Phase 11 — Ambiguity resolution workflow
# ---------------------------------------------------------------------------

RESOLUTION_TYPES = {
    "SOURCE_CONFIRMS_PER_DAY", "SOURCE_CONFIRMS_PER_DOSE",
    "SOURCE_CONFIRMS_FIXED_DAILY", "SOURCE_CONFIRMS_FIXED_SINGLE",
    "SOURCE_REMAINS_AMBIGUOUS", "SOURCE_TEXT_INCOMPLETE",
    "TABLE_CONTEXT_REQUIRED", "EXTRACTION_DEFECT",
}


@dataclass
class AmbiguityResolution:
    resolution_id: str
    semantics_id: str
    regimen_id: str
    resolution_type: str
    exact_quote: str
    source_pdf: str
    source_page: str
    rationale: str
    reviewer_identity: str
    created_at: str

    def __post_init__(self) -> None:
        if self.resolution_type not in RESOLUTION_TYPES:
            raise ValueError(f"invalid resolution_type: {self.resolution_type}")

    def to_dict(self) -> dict:
        return asdict(self)
