"""Phase 9 — Sandbox integration: DoseSemantics -> calculation eligibility & trace.

Bridges the RC-030 semantics layer (semantics_parser.py) into the existing
calculation trace engine (calculator.py) without modifying its arithmetic.
A resolved DoseSemantics is converted into a DoseExpression whose
denominator_time is no longer None — that's what previously forced BLOCKED —
so the same, already-tested calculate() now proceeds for every source-backed
resolvable case.
"""
from __future__ import annotations

from typing import Optional

from .models import DoseExpression, DoseCalculationTrace, PARSED, UNPARSED, BLOCKED, OK
from .semantics_models import DoseSemantics
from .calculator import calculate, apply_max_dose

ELIGIBLE = "ELIGIBLE"
INELIGIBLE_BLOCKED = "BLOCKED"

_RESOLVABLE_TYPES = {
    "WEIGHT_PER_DAY", "WEIGHT_PER_DOSE", "FIXED_PER_DAY", "FIXED_PER_DOSE",
    "RANGE_PER_DAY", "RANGE_PER_DOSE",
}
_UNRESOLVABLE_TYPES = {"UNPARSED", "AMBIGUOUS", "MISSING", "NOT_APPLICABLE"}


def eligibility(ds: DoseSemantics, latest_version: Optional[int] = None) -> tuple[str, list[str]]:
    """Return (ELIGIBLE|BLOCKED, reasons)."""
    reasons: list[str] = []
    if ds.semantic_type in _UNRESOLVABLE_TYPES:
        reasons.append(f"UNRESOLVABLE_SEMANTIC_TYPE:{ds.semantic_type}")
    if ds.numerator_unit is None:
        reasons.append("UNSUPPORTED_UNIT")
    if latest_version is not None and ds.regimen_version < latest_version:
        reasons.append(f"STALE_SEMANTIC_VERSION:{ds.regimen_version}<{latest_version}")
    return (INELIGIBLE_BLOCKED if reasons else ELIGIBLE), reasons


def semantics_to_expression(ds: DoseSemantics) -> DoseExpression:
    time_denom = ds.time_denominator if ds.semantic_type in _RESOLVABLE_TYPES else None
    return DoseExpression(
        numeric_min=ds.numeric_min, numeric_max=ds.numeric_max,
        numerator_unit=ds.numerator_unit, denominator_weight=ds.weight_denominator,
        denominator_time=time_denom, per_dose_or_per_day=time_denom,
        frequency=ds.frequency, max_single_dose=ds.max_single_dose, max_daily_dose=ds.max_daily_dose,
        source_expression=ds.source_expression,
        parser_status=PARSED if ds.semantic_type in _RESOLVABLE_TYPES else UNPARSED,
    )


def calculate_from_semantics(ds: DoseSemantics, weight_kg: float,
                              latest_version: Optional[int] = None) -> tuple[str, list[str], DoseCalculationTrace]:
    status, reasons = eligibility(ds, latest_version)
    expr = semantics_to_expression(ds)
    trace = calculate(expr, weight_kg=weight_kg)
    if status == INELIGIBLE_BLOCKED and trace.calculation_status == OK:
        # e.g. unit resolved but semantic_type itself is unresolvable/stale —
        # calculate() alone wouldn't know to block on those grounds.
        trace.calculation_status = BLOCKED
        trace.warnings.extend(reasons)
    if ds.max_daily_dose is not None or ds.max_single_dose is not None:
        apply_max_dose(trace, source_max_daily_dose=ds.max_daily_dose, source_max_single_dose=ds.max_single_dose)
    return status, reasons, trace
