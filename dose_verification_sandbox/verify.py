"""Phase 10-11 — Verification result assembly and owner comparison.

Builds the eight separate verdicts. clinical_approval is hard-coded to
NOT_APPROVED by DoseVerificationResult.__post_init__ and cannot be overridden
here — there is no code path in this module that sets it any other way.
"""
from __future__ import annotations

from .models import (
    DoseExpression, DoseCalculationTrace, DoseVerificationResult,
    PARSED, UNPARSED, BLOCKED, OK, PASS, FAIL, NOT_AVAILABLE, NEEDS_REVIEW,
)


def build_verification_result(
    regimen: dict,
    expr: DoseExpression,
    trace: DoseCalculationTrace,
) -> DoseVerificationResult:
    # A. SOURCE_FIDELITY — did we use exactly the regimen's stored dose/unit/frequency?
    source_fidelity = PASS if regimen.get("dose") is not None and (regimen.get("unit") or "") != "" else NOT_AVAILABLE

    # B. PARSING
    parsing = PASS if expr.parser_status == PARSED else FAIL

    # C. ARITHMETIC
    if trace.calculation_status == BLOCKED:
        arithmetic = BLOCKED
    elif trace.final_min_daily_dose is not None or trace.final_min_single_dose is not None:
        arithmetic = PASS
    else:
        arithmetic = NOT_AVAILABLE

    # D. UNIT_CONSISTENCY
    if expr.parser_status == UNPARSED:
        unit_consistency = FAIL
    elif expr.numerator_unit is not None:
        unit_consistency = PASS
    else:
        unit_consistency = NOT_AVAILABLE

    # E. MAX_DOSE — if arithmetic never completed (BLOCKED), max-dose was never
    # assessed at all; only report PASS/NOT_AVAILABLE when a value actually exists.
    if trace.calculation_status == BLOCKED:
        max_dose = NOT_AVAILABLE
    else:
        max_dose = NOT_AVAILABLE if trace.max_dose_reason == "MAX_DOSE_NOT_AVAILABLE" else PASS

    # F. ROUNDING — NOT_APPLIED is a deliberate, valid state, reported as NOT_AVAILABLE
    # (no governed rounding policy exists yet — see DOSE_ROUNDING_POLICY.md)
    if trace.calculation_status == BLOCKED:
        rounding = NOT_AVAILABLE
    else:
        rounding = NOT_AVAILABLE if trace.rounding_status == "NOT_APPLIED" else PASS

    # G. FORMULATION_CONVERSION — assembled_regimens carries no concentration data
    formulation_conversion = NOT_AVAILABLE

    # Needs-review reasons recorded upstream by the assembly engine downgrade the
    # verdict from a clean PASS to NEEDS_REVIEW where relevant.
    if regimen.get("needs_review_reasons"):
        if source_fidelity == PASS:
            source_fidelity = NEEDS_REVIEW

    return DoseVerificationResult(
        source_fidelity=source_fidelity,
        parsing=parsing,
        arithmetic=arithmetic,
        unit_consistency=unit_consistency,
        max_dose=max_dose,
        rounding=rounding,
        formulation_conversion=formulation_conversion,
    )
