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
    "RESOLVED_BY_FREQUENCY_ONE",   # LEGACY (RC-030 repair Phase 2 disabled the freq==1 shortcut in the
                                   # parser). Kept only so previously-stored classification artifacts still
                                   # validate; the current parser never emits it.
    "AMBIGUOUS_NO_SIGNAL",         # no explicit textual signal found in the source window
    "AMBIGUOUS_CONFLICTING_SIGNAL",  # both per-day and per-dose signals found in the same window
    "NOT_APPLICABLE",
}

# RC-030 repair Phase 1 — schedule period, kept strictly separate from dose basis.
SCHEDULE_PERIODS = {
    "DAILY", "WEEKLY", "EVERY_N_HOURS", "EVERY_OTHER_DAY", "SINGLE", "CUSTOM", "UNKNOWN",
}

# RC-030 repair Phases 2/5 — schedule/fail-closed risk flags carried on the semantics record.
SCHEDULE_RISK_FLAGS = {
    "EXPLICIT_DOSE_BASIS_MISSING",    # markerless dose; freq==1 no longer rescues it
    "WEEKLY_SCHEDULE_UNSUPPORTED",
    "NON_DAILY_SCHEDULE",
    "SUB_DAILY_FREQUENCY",
    "LOADING_MAINTENANCE_UNRESOLVED",
    "RANGE_VALUE_COLLAPSED_UPSTREAM",
    "NORMALIZER_RANGE_UPPER_BOUND_DROPPED",
    "TABLE_CONTEXT_REQUIRED",
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
    # RC-030 repair — additive schedule/range separation (all optional, default-None,
    # so every existing DoseSemantics(...) constructor keeps working unchanged).
    schedule_period: Optional[str] = None          # one of SCHEDULE_PERIODS
    administrations_per_day: Optional[float] = None  # informational only; never activates calculation
    interval_hours: Optional[float] = None
    schedule_risk_flags: list = field(default_factory=list)
    range_min_source: Optional[float] = None       # lower bound recovered from source_quote text
    range_max_source: Optional[float] = None        # upper bound recovered from source_quote text
    range_collapsed_upstream: bool = False          # True when source has a range but structured dose is scalar

    def __post_init__(self) -> None:
        if self.semantic_type not in SEMANTIC_TYPES:
            raise ValueError(f"invalid semantic_type: {self.semantic_type}")
        if self.ambiguity_status not in AMBIGUITY_STATUSES:
            raise ValueError(f"invalid ambiguity_status: {self.ambiguity_status}")
        if self.schedule_period is not None and self.schedule_period not in SCHEDULE_PERIODS:
            raise ValueError(f"invalid schedule_period: {self.schedule_period}")
        for f_ in self.schedule_risk_flags:
            if f_ not in SCHEDULE_RISK_FLAGS:
                raise ValueError(f"invalid schedule_risk_flag: {f_}")

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
