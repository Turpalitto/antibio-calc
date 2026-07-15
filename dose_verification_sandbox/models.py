"""Data model for the Dose Calculation Verification Sandbox.

QA / RESEARCH ONLY. See DOSE_VERIFICATION_SANDBOX_SPEC.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Any


# ---------------------------------------------------------------------------
# Phase 2 — Input model
# ---------------------------------------------------------------------------

class UnsupportedInput(Exception):
    """Raised when an input cannot be safely accepted. Never caught to guess a value."""


@dataclass
class DoseVerificationInput:
    diagnosis_code: str
    diagnosis_system: str  # "MKB10" (repository-supported equivalent used by assembled_regimens.icd_mkb)
    diagnosis_display: str
    antibiotic_id: str  # antibiotic name, used as identifier (no separate antibiotic master table exists)
    antibiotic_name: str
    age_value: float
    age_unit: str  # "years" | "months" | "days"
    weight_kg: float
    selected_regimen_id: str
    selected_regimen_version: int
    route: Optional[str] = None
    dosage_form: Optional[str] = None
    renal_function: Optional[str] = None
    sex: Optional[str] = None
    pregnancy: Optional[bool] = None

    def validate(self) -> None:
        if self.weight_kg is None or self.weight_kg <= 0:
            raise UnsupportedInput("UNSUPPORTED_INPUT: weight_kg must be positive")
        if self.age_value is None or self.age_value < 0:
            raise UnsupportedInput("UNSUPPORTED_INPUT: age_value must be non-negative")
        if self.age_unit not in ("years", "months", "days"):
            raise UnsupportedInput(f"UNSUPPORTED_INPUT: unsupported age_unit '{self.age_unit}'")
        if not self.diagnosis_code:
            raise UnsupportedInput("UNSUPPORTED_INPUT: diagnosis_code is required")
        if not self.antibiotic_name:
            raise UnsupportedInput("UNSUPPORTED_INPUT: antibiotic_name is required")
        if not self.selected_regimen_id:
            raise UnsupportedInput("UNSUPPORTED_INPUT: selected_regimen_id is required")


# ---------------------------------------------------------------------------
# Phase 4 — Dose expression model
# ---------------------------------------------------------------------------

PARSED = "PARSED"
UNPARSED = "UNPARSED"


@dataclass
class DoseExpression:
    numeric_min: Optional[float]
    numeric_max: Optional[float]
    numerator_unit: Optional[str]          # mg | g | IU | % | mL | None
    denominator_weight: bool               # True if per-kg
    denominator_time: Optional[str]        # "dose" | "day" | None (None = ambiguous/unknown)
    per_dose_or_per_day: Optional[str]      # mirrors denominator_time; kept distinct per spec field list
    frequency: Optional[float]              # administrations per day
    max_single_dose: Optional[float]
    max_daily_dose: Optional[float]
    source_expression: str                  # raw "{dose} {unit}" as stored in source
    parser_status: str                      # PARSED | UNPARSED


# ---------------------------------------------------------------------------
# Phase 5-9 — Calculation trace
# ---------------------------------------------------------------------------

BLOCKED = "BLOCKED"
OK = "OK"


@dataclass
class TraceStep:
    label: str
    formula: str
    operands: dict
    result: Any
    unit: Optional[str] = None


@dataclass
class DoseCalculationTrace:
    calculation_status: str                 # OK | BLOCKED
    steps: list = field(default_factory=list)   # list[TraceStep]
    warnings: list = field(default_factory=list)
    final_min_single_dose: Optional[float] = None
    final_max_single_dose: Optional[float] = None
    final_min_daily_dose: Optional[float] = None
    final_max_daily_dose: Optional[float] = None
    final_frequency: Optional[float] = None
    final_unit: Optional[str] = None
    rounding_status: str = "NOT_APPLIED"
    exact_result_preserved: bool = True
    max_dose_reason: Optional[str] = None   # SOURCE_MAX_DAILY_DOSE | MAX_DOSE_NOT_AVAILABLE | None

    def add_step(self, label: str, formula: str, operands: dict, result: Any, unit: Optional[str] = None) -> None:
        self.steps.append(TraceStep(label, formula, operands, result, unit))


# ---------------------------------------------------------------------------
# Phase 10 — Verification result
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
NOT_AVAILABLE = "NOT_AVAILABLE"
NEEDS_REVIEW = "NEEDS_REVIEW"
NOT_APPROVED = "NOT_APPROVED"

ALLOWED_TECHNICAL_STATUSES = {PASS, FAIL, BLOCKED, NOT_AVAILABLE, NEEDS_REVIEW}


@dataclass
class DoseVerificationResult:
    source_fidelity: str
    parsing: str
    arithmetic: str
    unit_consistency: str
    max_dose: str
    rounding: str
    formulation_conversion: str
    clinical_approval: str = NOT_APPROVED  # always NOT_APPROVED until governed physician approval exists

    def __post_init__(self) -> None:
        for name, value in (
            ("source_fidelity", self.source_fidelity),
            ("parsing", self.parsing),
            ("arithmetic", self.arithmetic),
            ("unit_consistency", self.unit_consistency),
            ("max_dose", self.max_dose),
            ("rounding", self.rounding),
            ("formulation_conversion", self.formulation_conversion),
        ):
            if value not in ALLOWED_TECHNICAL_STATUSES:
                raise ValueError(f"invalid status for {name}: {value}")
        if self.clinical_approval != NOT_APPROVED:
            raise ValueError("clinical_approval must remain NOT_APPROVED — no governed physician approval exists")


# ---------------------------------------------------------------------------
# Phase 11 — Owner comparison
# ---------------------------------------------------------------------------

CALCULATION_MATCH = "CALCULATION_MATCH"
CALCULATION_MISMATCH = "CALCULATION_MISMATCH"
SOURCE_DATA_MISMATCH = "SOURCE_DATA_MISMATCH"
DOSE_PARSE_FAILURE = "DOSE_PARSE_FAILURE"
UNIT_ERROR = "UNIT_ERROR"
FREQUENCY_ERROR = "FREQUENCY_ERROR"
MAX_DOSE_ERROR = "MAX_DOSE_ERROR"
ROUNDING_ERROR = "ROUNDING_ERROR"
NEEDS_INFO = "NEEDS_INFO"

OWNER_CLASSIFICATIONS = {
    CALCULATION_MATCH, CALCULATION_MISMATCH, SOURCE_DATA_MISMATCH, DOSE_PARSE_FAILURE,
    UNIT_ERROR, FREQUENCY_ERROR, MAX_DOSE_ERROR, ROUNDING_ERROR, NEEDS_INFO,
}


@dataclass
class OwnerComparison:
    expected_single_dose: Optional[float] = None
    expected_daily_dose: Optional[float] = None
    expected_frequency: Optional[float] = None
    expected_unit: Optional[str] = None
    owner_note: str = ""
    classification: Optional[str] = None

    def compare(self, trace: DoseCalculationTrace) -> dict:
        out = {"absolute_difference": None, "percentage_difference": None,
               "unit_mismatch": None, "frequency_mismatch": None}
        if self.expected_daily_dose is not None and trace.final_max_daily_dose is not None:
            out["absolute_difference"] = round(abs(self.expected_daily_dose - trace.final_max_daily_dose), 6)
            if trace.final_max_daily_dose != 0:
                out["percentage_difference"] = round(
                    100.0 * out["absolute_difference"] / trace.final_max_daily_dose, 4
                )
        if self.expected_unit is not None and trace.final_unit is not None:
            out["unit_mismatch"] = self.expected_unit != trace.final_unit
        if self.expected_frequency is not None and trace.final_frequency is not None:
            out["frequency_mismatch"] = self.expected_frequency != trace.final_frequency
        return out

    def set_classification(self, value: str) -> None:
        if value not in OWNER_CLASSIFICATIONS:
            raise ValueError(f"unknown owner classification: {value}")
        self.classification = value


# ---------------------------------------------------------------------------
# Phase 12 — Defect recording
# ---------------------------------------------------------------------------

ISSUE_STATUSES = {"OPEN", "CONFIRMED", "NOT_REPRODUCIBLE", "FIX_PROPOSED", "FIXED", "RETEST_REQUIRED", "CLOSED"}


@dataclass
class DoseCalculationIssue:
    issue_id: str
    diagnosis_code: str
    regimen_id: str
    regimen_version: int
    antibiotic: str
    patient_input: dict
    source_expression: str
    system_calculation_trace: dict
    expected_value: dict
    difference: dict
    issue_category: str
    severity: str
    source_pdf: str
    source_page: str
    created_by: str
    created_at: str
    status: str = "OPEN"

    def __post_init__(self) -> None:
        if self.status not in ISSUE_STATUSES:
            raise ValueError(f"invalid issue status: {self.status}")

    def to_dict(self) -> dict:
        return asdict(self)
