"""All Clinical Decision Engine dataclasses and enums.

Source of truth: docs/superpowers/specs/clinical-decision-engine-v1.md
section 5 (Public Interfaces) and section 8.3 (EngineError).

Every dataclass is frozen + slots (Constitutional Invariant #4 — mutation
only via dataclasses.replace()). This module does no I/O and contains no
clinical logic; it only defines shapes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# 5.1 Enums
# ---------------------------------------------------------------------------


class ValidationPolicy(Enum):
    STRICT = "strict"
    ALLOW_REVIEW = "allow_review"
    DEBUG = "debug"
    AUDIT = "audit"


class SafetyLevel(Enum):
    WARNING = "warning"
    ABSOLUTE_CONTRAINDICATION = "absolute_contraindication"


class InteractionSeverity(Enum):
    UNKNOWN = 0  # cannot classify -- NOT defaulted to moderate
    MINOR = 1
    MODERATE = 2
    MAJOR = 3
    CONTRAINDICATED = 4


class PregnancyCategory(Enum):
    PROHIBITED = "prohibited"
    CAUTION = "caution"
    ALLOWED = "allowed"
    UNKNOWN = "unknown"


class OrganAdjustmentLevel(Enum):
    """Load-time classification of an organ-adjustment free-text field.

    Invariant #13 forbids parsing clinical prose at query runtime, so the
    keyword classification happens ONCE at preparation time in
    DrugReferenceReader (exactly like PregnancyCategory) and the stage only
    ever reads this enum. Without it, a dose of "Противопоказан при тяжёлой
    печёночной недостаточности" and "Не требуется" were indistinguishable at
    runtime and both degraded to the same MONITOR_CLOSELY advisory.
    """

    PROHIBITED = "prohibited"   # source text states a contraindication
    CAUTION = "caution"         # source text states caution / mandatory action
    NONE = "none"               # source text states no adjustment needed
    UNKNOWN = "unknown"         # text present but not classifiable, or absent



class RecommendationOutcome(Enum):
    ACCEPTED = "accepted"
    EXCLUDED = "excluded"
    WARNING = "warning"


class ClinicalPriority(Enum):
    FIRST_CHOICE = "first_choice"
    ALTERNATIVE = "alternative"
    RESERVE = "reserve"
    SALVAGE = "salvage"
    EXPERIMENTAL = "experimental"


class DecisionCode(Enum):
    ALLERGY = "allergy"
    PREGNANCY = "pregnancy"
    RENAL = "renal"
    AGE = "age"
    THERAPY_LINE = "therapy_line"
    POPULATION = "population"
    INTERACTION = "interaction"
    NO_MATCH = "no_match"
    DIAGNOSIS_RESOLVED = "diagnosis_resolved"
    DRUG_UNKNOWN = "drug_unknown"
    DOSE_UNCALCULABLE = "dose_uncalculable"
    CI = "ci"
    HEPATIC = "hepatic"


class ConfidenceLevel(Enum):
    """Discrete confidence -- no false precision."""

    NONE = 0.0
    LOW = 0.25
    MEDIUM = 0.5
    HIGH = 0.75
    FULL = 1.0


class NoteSeverity(Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class DoseCalculationMethod(Enum):
    FIXED = "fixed"
    MG_PER_KG = "mg_per_kg"
    RENAL_ADJUSTED = "renal_adjusted"
    HEPATIC_ADJUSTED = "hepatic_adjusted"
    UNCALCULATED = "uncalculated"


class SafetyAction(Enum):
    """What the UI/physician should do."""

    STOP_IMMEDIATELY = "stop_immediately"
    AVOID_IF_POSSIBLE = "avoid_if_possible"
    MONITOR_CLOSELY = "monitor_closely"
    INFORM_PATIENT = "inform_patient"


# Ordered most severe first. Reduces a set of actions to its worst member.
SAFETY_ACTION_SEVERITY: tuple[SafetyAction, ...] = (
    SafetyAction.STOP_IMMEDIATELY,
    SafetyAction.AVOID_IF_POSSIBLE,
    SafetyAction.MONITOR_CLOSELY,
    SafetyAction.INFORM_PATIENT,
)


def most_severe_action(actions: "tuple[SafetyAction, ...] | list[SafetyAction]") -> SafetyAction | None:
    """Worst action in a collection, or None when empty."""
    present = set(actions)
    for action in SAFETY_ACTION_SEVERITY:
        if action in present:
            return action
    return None


# ---------------------------------------------------------------------------
# 8.3 EngineError — infrastructure errors only (clinical no-data is NOT this)
# ---------------------------------------------------------------------------


class EngineErrorCode(Enum):
    SQLITE_NOT_FOUND = "sqlite_not_found"
    SQLITE_CORRUPT = "sqlite_corrupt"
    DRUG_REFERENCE_NOT_FOUND = "drug_ref_not_found"
    DIAGNOSIS_INDEX_NOT_FOUND = "diag_index_not_found"
    SCORE_PROFILE_NOT_FOUND = "score_profile_not_found"
    RESOURCE_PARSE_ERROR = "resource_parse_error"
    READER_INIT_FAILED = "reader_init_failed"
    # Milestone 13 (Release Readiness): the configured diagnosis_index is not
    # physician-curated (AUTO_GENERATED_DRAFT / PARTIALLY_CURATED) and
    # strict_mode forbids running production on uncurated clinical data.
    RESOURCE_NOT_CURATED = "resource_not_curated"


class EngineError(Exception):
    """Infrastructure error. Clinical no-data is NOT EngineError."""

    def __init__(self, code: EngineErrorCode, detail: str, stage: str | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.stage = stage


# ---------------------------------------------------------------------------
# 5.2 Input dataclasses
# ---------------------------------------------------------------------------

# A GFR the engine is willing to act on: a plain number, optionally prefixed
# with an eGFR/CKF label and/or suffixed with a ml/min unit. Deliberately
# strict -- an inequality, a range or free text yields None so the caller can
# degrade loudly instead of dosing off a guessed number.
_GRF_PATTERN = re.compile(
    r"^\s*(?:e?gfr|скф|kk|кк)?\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:мл/мин|мл\/мин|ml/min)?\s*$",
    re.IGNORECASE,
)


def coerce_gfr(value: float | str | None) -> float | None:
    """Coerce a GFR input (number or string) to ml/min, or None if unusable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _GRF_PATTERN.match(value)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


@dataclass(frozen=True, slots=True)
class Patient:
    age: float | None = None
    weight_kg: float | None = None
    pregnant: bool = False
    # GFR in ml/min. Typed `float | str` on purpose: api/contract.py declares
    # this field `str | None` and api/service.py assigns that string straight
    # in, so a plain `float` annotation made the model a loaded trap (a
    # "45" would silently become truthy-but-unusable). Consumers must read
    # `gfr_ml_min` (coerced) or `gfr_unparseable`, never the raw field.
    renal_function: float | str | None = None
    hepatic_impairment: bool = False
    allergies: tuple[str, ...] = ()  # drug classes
    current_meds: tuple[str, ...] = ()  # for InteractionCheck

    @property
    def gfr_ml_min(self) -> float | None:
        """renal_function coerced to a GFR in ml/min, or None if unusable.

        Accepts a number, or a string carrying a plain number with an
        optional ml/min unit ("12", "12.5", "12 мл/мин", "eGFR 30"). Anything
        else -- a label ("норма"), an inequality (">90", "30-45") or a value
        with extra prose -- returns None rather than guessing. Callers must
        treat None + a non-None raw value as degraded data, not as "no renal
        data" (see `gfr_unparseable`).
        """
        return coerce_gfr(self.renal_function)

    @property
    def gfr_unparseable(self) -> bool:
        """True when renal data was supplied but could not be read as a GFR."""
        return self.renal_function is not None and self.gfr_ml_min is None


@dataclass(frozen=True, slots=True)
class Preferences:
    therapy_line: str | None = None
    route_preference: str | None = None
    population: str | None = None


@dataclass(frozen=True, slots=True)
class PatientQuery:
    diagnosis: str | None = None
    icd10: str | None = None
    patient: Patient = field(default_factory=Patient)
    preferences: Preferences = field(default_factory=Preferences)


# ---------------------------------------------------------------------------
# 5.3 Domain objects (readers return these)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DiagnosisEntry:
    guideline_id: str
    diagnosis_name: str
    icd10_codes: tuple[str, ...]
    guideline_title: str
    guideline_year: int | None
    guideline_revision_date: str | None  # full date, not just year
    source_url: str


@dataclass(frozen=True, slots=True)
class DrugForm:
    form_type: str
    concentration: str
    concentration_mg_per_ml: float | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class DilutionRoute:
    solvent_options: tuple[dict[str, Any], ...]
    concentration_standard_mg_ml: float | None = None
    administration_time_min: float | None = None
    infusion_time_min: float | None = None
    contraindications: str | None = None
    cautions: str | None = None
    steps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PediatricDosing:
    mg_per_kg_day: float | None = None
    max_daily_mg: float | None = None
    weight_min_kg: float | None = None
    weight_max_kg: float | None = None
    age_min: str | None = None
    age_max: str | None = None
    freq_per_day: int | None = None


@dataclass(frozen=True, slots=True)
class DrugInfo:
    drug_ref: str
    inn: str
    drug_class: str
    renal_adjustment: str | None
    hepatic_adjustment: str | None
    pregnancy_category: PregnancyCategory
    age_restriction_min: str | None
    age_restriction_max: str | None
    contraindications: str | None
    interactions: str | None
    monitoring: str | None
    forms: tuple[DrugForm, ...]
    dilution: dict[str, DilutionRoute]
    pediatric_dosing: PediatricDosing | None
    # Load-time classification of the two organ-adjustment free-text fields
    # (see OrganAdjustmentLevel). Populated by DrugReferenceReader; the
    # runtime stages read the enum, never the prose.
    renal_adjustment_level: OrganAdjustmentLevel = OrganAdjustmentLevel.UNKNOWN
    hepatic_adjustment_level: OrganAdjustmentLevel = OrganAdjustmentLevel.UNKNOWN
    # Verbatim source text behind `pregnancy_category`. Kept so the safety
    # filter can show the physician WHY a drug was excluded, including
    # trimester-conditional wording that a bare enum value would hide.
    pregnancy_source_text: str | None = None


@dataclass(frozen=True, slots=True)
class RecommendationCandidate:
    regimen_id: str
    guideline_id: str
    drug_normalized: str
    drug_ref: str | None
    dose: float | None
    dose_unit: str
    route: str
    frequency: float | None
    duration_min: float | None
    duration_max: float | None
    duration_recommended: float | None
    therapy_line: str
    adult: bool
    child: bool
    pregnancy: bool | None
    renal_adjustment: bool
    atc_code: str
    confidence: float
    validation_verdict: str
    source_pdf: str
    source_page: str
    source_quote: str
    # Provenance section of the quote. Populated from the source row when it
    # carries one; otherwise SOURCE_SECTION_UNAVAILABLE -- never a bare "",
    # which is indistinguishable from "the source section was empty" and
    # silently breaks the Clinical Traceability Rule (L-5).
    source_section: str
    diagnosis: str
    mkb: str
    guideline_year: int | None  # from DiagnosisEntry (diagnosis_index), not SQLite


# Loud placeholder for provenance the source data does not carry.
SOURCE_SECTION_UNAVAILABLE = "UNAVAILABLE_IN_SOURCE"


# ---------------------------------------------------------------------------
# 5.4 Safety, Trace, Dose, Confidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SafetyFlag:
    level: SafetyLevel
    code: str  # "ALLERGY", "PREGNANCY_CI", ...
    message: str  # human-readable
    drug_ref: str
    stage: str  # which stage raised it
    action: SafetyAction  # what physician should do
    requires_physician_acknowledgement: bool  # for Flutter UI confirmation


@dataclass(frozen=True, slots=True)
class Evidence:
    source_pdf: str
    source_page: str
    source_quote: str
    source_section: str
    guideline_title: str | None
    guideline_year: int | None
    guideline_revision_date: str | None  # full date
    source_url: str | None


@dataclass(frozen=True, slots=True)
class StageTrace:
    stage_name: str
    decision_code: DecisionCode
    reason: str
    evidence: Evidence | None = None
    decision_confidence: ConfidenceLevel = ConfidenceLevel.FULL
    # immutable + append-only (invariant #6)


@dataclass(frozen=True, slots=True)
class DoseDetail:
    calculated_dose_mg: float | None
    dose_unit: str
    frequency_per_day: float | None
    duration_days: float | None
    max_daily_mg: float | None
    calculation_method: DoseCalculationMethod
    adjustment_applied: str | None
    calculation_note: str | None
    adjustment_history: tuple[str, ...] = ()  # ["base: 500mg", "renal: 250mg", "final: 250mg"]
    # False whenever an adjustment the patient's organ status requires could
    # not be applied, because the adjustment data is unstructured prose
    # (RENAL_ADJ_UNPARSED / HEPATIC_ADJ_UNPARSED). A number is still emitted
    # (degraded mode never silently excludes), but the consumer MUST know it
    # is not a patient-specific dose. True = the emitted dose reflects the
    # patient's organ function/impairment.
    dose_is_patient_specific: bool = True


@dataclass(frozen=True, slots=True)
class ConfidenceBreakdown:
    source: float  # SQLite overall_confidence
    decision: float  # mean of stage DecisionConfidence values
    dose: float  # dose calculation state
    completeness: float  # warning flags penalty
    evidence: float  # guideline recency
    final: float  # weighted sum


# ---------------------------------------------------------------------------
# 5.5 Recommendation and Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Recommendation:
    candidate: RecommendationCandidate
    dose: DoseDetail | None
    safety_flags: tuple[SafetyFlag, ...]
    interaction_severity: InteractionSeverity | None
    outcome: RecommendationOutcome | None = None
    rank: int | None = None
    score: float | None = None
    score_breakdown: dict[str, float] = field(default_factory=dict)
    trace: tuple[StageTrace, ...] = ()
    confidence: float = 0.0
    confidence_breakdown: ConfidenceBreakdown | None = None
    clinical_priority: ClinicalPriority | None = None


@dataclass(frozen=True, slots=True)
class EngineNote:
    code: str
    message: str
    stage: str
    severity: NoteSeverity


@dataclass(frozen=True, slots=True)
class SafetySummary:
    """Aggregate safety information for a whole result set.

    H-4: the engine computed every one of these signals and the transport
    layer dropped them, so an answer carrying PREGNANCY_CAUTION or
    RENAL_ADJ_UNPARSED was indistinguishable from a clean one. The engine
    therefore publishes its own, transport-independent summary; the API layer
    must pass it through rather than recompute (or drop) it.

    `status` is the engine's own verdict on the returned set:
      "CLEARED"         -- no flag, every dose patient-specific
      "REVIEW_REQUIRED" -- at least one warning / acknowledgement / dose that
                           is not patient-specific; a physician must review
                           before the recommendation is used.
    """

    status: str
    requires_physician_review: bool
    total_flags: int
    flag_counts: dict[str, int]
    flag_codes: tuple[str, ...]
    most_severe_action: SafetyAction | None
    actions: tuple[SafetyAction, ...]  # distinct, most severe first
    requires_physician_acknowledgement: int
    absolute_contraindications: int
    dose_is_patient_specific: bool  # False if ANY accepted dose is not

    @classmethod
    def from_result(
        cls,
        safety_flags: "tuple[SafetyFlag, ...] | list[SafetyFlag]",
        accepted: "tuple[Recommendation, ...] | list[Recommendation]" = (),
    ) -> "SafetySummary":
        flags = tuple(safety_flags)
        counts: dict[str, int] = {}
        for f in flags:
            counts[f.code] = counts.get(f.code, 0) + 1
        actions = tuple(a for a in SAFETY_ACTION_SEVERITY if any(f.action is a for f in flags))
        acks = sum(1 for f in flags if f.requires_physician_acknowledgement)
        absolutes = sum(1 for f in flags if f.level is SafetyLevel.ABSOLUTE_CONTRAINDICATION)
        dose_ok = all(
            (getattr(rec, "dose", None) is None)
            or getattr(getattr(rec, "dose", None), "dose_is_patient_specific", True)
            for rec in accepted
        )
        review = bool(flags) or not dose_ok
        return cls(
            status="REVIEW_REQUIRED" if review else "CLEARED",
            requires_physician_review=review,
            total_flags=len(flags),
            flag_counts=counts,
            flag_codes=tuple(counts),
            most_severe_action=actions[0] if actions else None,
            actions=actions,
            requires_physician_acknowledgement=acks,
            absolute_contraindications=absolutes,
            dose_is_patient_specific=dose_ok,
        )


@dataclass(frozen=True, slots=True)
class EngineMetadata:
    decision_engine_version: str  # "1.0.0" -- engine SEMVER
    knowledge_dataset_version: str  # "KB-2026-07-09" -- dataset version, not file hash
    normalizer_version: str  # from SQLite rows
    dictionary_version: str  # medical_dictionary/metadata.json version
    guideline_version: str  # guideline set version (from diagnosis_index)


@dataclass(frozen=True, slots=True)
class EngineRuntime:
    generated_at: str  # ISO 8601 timestamp
    elapsed_ms: float
    profile: ValidationPolicy
    pipeline_time_breakdown: dict[str, float] = field(default_factory=dict)
    # {"diagnosis": 1.2, "safety": 4.1, ...}


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Future LLM/logging integration point."""

    patient: Patient
    query: PatientQuery
    engine_metadata: EngineMetadata
    runtime: EngineRuntime
    profile: ValidationPolicy


@dataclass(frozen=True, slots=True)
class RecommendationSet:
    accepted: tuple[Recommendation, ...]
    excluded: tuple[tuple[Recommendation, str], ...]
    warnings: tuple[SafetyFlag, ...]
    traces: tuple[StageTrace, ...]
    safety_flags: tuple[SafetyFlag, ...]
    metadata: EngineMetadata
    runtime: EngineRuntime
    decision_context: DecisionContext
    engine_notes: tuple[EngineNote, ...]
    query: PatientQuery
    elapsed_ms: float
    # H-4: always populated by Engine.recommend(). Kept optional so existing
    # callers/constructed sets (and the curated wrapper) stay constructible;
    # a missing summary must never be read as "no safety information".
    safety_summary: SafetySummary | None = None


def _dc_to_primitive(value: Any) -> Any:
    """Recursively turn dataclasses/enums/tuples into JSON-safe primitives."""
    if hasattr(value, "__dataclass_fields__"):
        return {f: _dc_to_primitive(getattr(value, f)) for f in value.__dataclass_fields__}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_dc_to_primitive(v) for v in value]
    if isinstance(value, dict):
        return {k: _dc_to_primitive(v) for k, v in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class DecisionReport:
    """Complete clinical decision report. Exportable."""

    query: PatientQuery
    accepted: tuple[Recommendation, ...]
    excluded: tuple[tuple[Recommendation, str], ...]
    warnings: tuple[SafetyFlag, ...]
    traces: tuple[StageTrace, ...]
    confidence_breakdowns: dict[str, ConfidenceBreakdown]
    metadata: EngineMetadata
    runtime: EngineRuntime
    engine_notes: tuple[EngineNote, ...]
    safety_summary: SafetySummary | None = None

    def to_dict(self) -> dict[str, Any]:
        return _dc_to_primitive(self)

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    # to_pdf() deferred to v2 (requires rendering library)
