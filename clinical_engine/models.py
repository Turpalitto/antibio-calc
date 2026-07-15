"""All Clinical Decision Engine dataclasses and enums.

Source of truth: docs/superpowers/specs/clinical-decision-engine-v1.md
section 5 (Public Interfaces) and section 8.3 (EngineError).

Every dataclass is frozen + slots (Constitutional Invariant #4 — mutation
only via dataclasses.replace()). This module does no I/O and contains no
clinical logic; it only defines shapes.
"""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class Patient:
    age: float | None = None
    weight_kg: float | None = None
    pregnant: bool = False
    renal_function: float | None = None  # GFR ml/min
    hepatic_impairment: bool = False
    allergies: tuple[str, ...] = ()  # drug classes
    current_meds: tuple[str, ...] = ()  # for InteractionCheck


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
    source_section: str  # v1: empty (SQLite lacks this column; future schema extension)
    diagnosis: str
    mkb: str
    guideline_year: int | None  # from DiagnosisEntry (diagnosis_index), not SQLite


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

    def to_dict(self) -> dict[str, Any]:
        return _dc_to_primitive(self)

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    # to_pdf() deferred to v2 (requires rendering library)
