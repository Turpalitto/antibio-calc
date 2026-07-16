"""RC-030 Evidence Validation, Phase 9 — semantic store status model.

Wraps a DoseSemantics record (parser output) with an explicit validation
status, calculation eligibility, and evidence level. Additive — does not
modify DoseSemantics or semantics_parser.py. A parser classification alone is
never enough to make a record calculation-eligible; see
RC030_PRECISION_METRICS.md for why every semantic type currently defaults to
UNVALIDATED + BLOCKED.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from .semantics_models import DoseSemantics
from .semantics_risk_audit import RiskAssessment

VALIDATION_STATUSES = {
    "UNVALIDATED", "RULE_VALIDATED", "SOURCE_VALIDATED", "STRUCTURE_VALIDATED",
    "HUMAN_FIDELITY_VALIDATED", "REJECTED", "AMBIGUOUS",
}

CALCULATION_ELIGIBILITY = {"BLOCKED", "QA_ELIGIBLE", "CLINICALLY_INELIGIBLE"}

EVIDENCE_LEVELS = {
    "NONE",              # no textual evidence located at all
    "ALGEBRAIC",         # resolved only via the frequency=1 shortcut, no textual signal
    "TEXTUAL_WEAK",      # textual signal found, but flagged high-risk by the Phase 3 audit
    "TEXTUAL_STRONG",    # textual signal found, clean (no risk factors), or multiple independent markers
}

# Per RC030_PRECISION_METRICS.md: no semantic type's Wilson-95%-lower-bound
# precision has been demonstrated to reach the required 99% threshold with
# the sample sizes achieved in this validation pass. This set is
# intentionally empty today; it exists so a future, adequately-powered
# validation run has a single place to record which types have actually
# cleared the bar.
TYPES_MEETING_PRECISION_THRESHOLD: set[str] = set()


@dataclass
class ValidatedDoseSemantics:
    parser_semantic_type: str
    validation_status: str
    calculation_eligibility: str
    evidence_level: str
    regimen_id: str
    regimen_version: int
    risk_factors: list

    def __post_init__(self) -> None:
        if self.validation_status not in VALIDATION_STATUSES:
            raise ValueError(f"invalid validation_status: {self.validation_status}")
        if self.calculation_eligibility not in CALCULATION_ELIGIBILITY:
            raise ValueError(f"invalid calculation_eligibility: {self.calculation_eligibility}")
        if self.evidence_level not in EVIDENCE_LEVELS:
            raise ValueError(f"invalid evidence_level: {self.evidence_level}")

    def to_dict(self) -> dict:
        return asdict(self)


_UNRESOLVABLE = {"UNPARSED", "AMBIGUOUS", "MISSING", "NOT_APPLICABLE"}
_RESOLVABLE = {"WEIGHT_PER_DAY", "WEIGHT_PER_DOSE", "FIXED_PER_DAY", "FIXED_PER_DOSE",
               "RANGE_PER_DAY", "RANGE_PER_DOSE"}


def validate(ds: DoseSemantics, risk: Optional[RiskAssessment] = None) -> ValidatedDoseSemantics:
    """Compute validation_status/calculation_eligibility/evidence_level for a
    DoseSemantics record. Never promotes a record to QA_ELIGIBLE on parser
    output alone — only if its semantic_type is in
    TYPES_MEETING_PRECISION_THRESHOLD (currently empty)."""
    risk_factors = risk.risk_factors if risk else []

    if ds.semantic_type in _UNRESOLVABLE:
        validation_status = "AMBIGUOUS" if ds.semantic_type == "AMBIGUOUS" else "UNVALIDATED"
        calculation_eligibility = "BLOCKED"
        evidence_level = "NONE"
    elif risk_factors:
        validation_status = "UNVALIDATED"
        calculation_eligibility = "BLOCKED"
        evidence_level = "TEXTUAL_WEAK"
    elif ds.ambiguity_status == "RESOLVED_BY_FREQUENCY_ONE":
        validation_status = "RULE_VALIDATED"  # the algebra itself is sound and needs no human check
        calculation_eligibility = (
            "QA_ELIGIBLE" if ds.semantic_type in TYPES_MEETING_PRECISION_THRESHOLD else "BLOCKED"
        )
        evidence_level = "ALGEBRAIC"
    else:
        validation_status = "RULE_VALIDATED"
        calculation_eligibility = (
            "QA_ELIGIBLE" if ds.semantic_type in TYPES_MEETING_PRECISION_THRESHOLD else "BLOCKED"
        )
        evidence_level = "TEXTUAL_STRONG"

    return ValidatedDoseSemantics(
        parser_semantic_type=ds.semantic_type,
        validation_status=validation_status,
        calculation_eligibility=calculation_eligibility,
        evidence_level=evidence_level,
        regimen_id=ds.regimen_id,
        regimen_version=ds.regimen_version,
        risk_factors=risk_factors,
    )
