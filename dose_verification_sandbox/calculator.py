"""Phase 5-9 — Deterministic calculation trace engine.

Every arithmetic step is recorded on the trace. No hidden arithmetic, no
inferred denominators, no clinical rounding invented, no max-dose applied
unless the source data actually carries one (it currently never does for
assembled_regimens.sqlite — see DOSE_VERIFICATION_SANDBOX_AUDIT.md §4/§7).
"""
from __future__ import annotations

from typing import Optional

from .models import DoseExpression, DoseCalculationTrace, UNPARSED, BLOCKED, OK


def calculate(expr: DoseExpression, weight_kg: float) -> DoseCalculationTrace:
    trace = DoseCalculationTrace(calculation_status=OK)

    if expr.parser_status == UNPARSED:
        trace.calculation_status = BLOCKED
        trace.warnings.append(f"DOSE_UNPARSED: source expression '{expr.source_expression}' could not be interpreted")
        return trace

    if expr.denominator_time is None:
        trace.calculation_status = BLOCKED
        trace.warnings.append(
            "AMBIGUOUS_PERIOD: source unit "
            f"'{expr.source_expression}' does not specify per-administration vs per-day; "
            "refusing to guess"
        )
        return trace

    weight_based = expr.denominator_weight
    trace.add_step(
        label="source",
        formula=expr.source_expression,
        operands={"numeric_min": expr.numeric_min, "numeric_max": expr.numeric_max,
                  "numerator_unit": expr.numerator_unit, "denominator_weight": weight_based,
                  "denominator_time": expr.denominator_time},
        result=expr.source_expression,
    )

    if weight_based:
        trace.add_step(label="weight", formula="input", operands={}, result=weight_kg, unit="kg")

    def scale(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return value * weight_kg if weight_based else value

    min_scaled = scale(expr.numeric_min)
    max_scaled = scale(expr.numeric_max)

    if expr.denominator_time == "day":
        trace.add_step(
            label="daily calculation",
            formula=(f"{expr.numeric_min} × {weight_kg}" if weight_based else f"{expr.numeric_min} (fixed)"),
            operands={"per_unit": expr.numeric_min, "weight_kg": weight_kg if weight_based else None},
            result=min_scaled, unit=f"{expr.numerator_unit}/day",
        )
        daily_min, daily_max = min_scaled, max_scaled
        if expr.frequency:
            single_min = daily_min / expr.frequency if daily_min is not None else None
            single_max = daily_max / expr.frequency if daily_max is not None else None
            trace.add_step(
                label="single dose",
                formula=f"{daily_min} ÷ {expr.frequency}",
                operands={"daily": daily_min, "frequency": expr.frequency},
                result=single_min, unit=expr.numerator_unit,
            )
        else:
            single_min = single_max = None
            trace.warnings.append("FREQUENCY_NOT_AVAILABLE: cannot derive single dose without frequency")
    else:  # denominator_time == "dose"
        single_min, single_max = min_scaled, max_scaled
        trace.add_step(
            label="single dose",
            formula=(f"{expr.numeric_min} × {weight_kg}" if weight_based else f"{expr.numeric_min} (fixed)"),
            operands={"per_unit": expr.numeric_min, "weight_kg": weight_kg if weight_based else None},
            result=single_min, unit=expr.numerator_unit,
        )
        if expr.frequency:
            daily_min = single_min * expr.frequency if single_min is not None else None
            daily_max = single_max * expr.frequency if single_max is not None else None
            trace.add_step(
                label="daily calculation",
                formula=f"{single_min} × {expr.frequency}",
                operands={"single": single_min, "frequency": expr.frequency},
                result=daily_min, unit=f"{expr.numerator_unit}/day",
            )
        else:
            daily_min = daily_max = None
            trace.warnings.append("FREQUENCY_NOT_AVAILABLE: cannot derive daily dose without frequency")

    # Phase 7 — maximum dose: assembled_regimens carries no max-dose columns.
    trace.max_dose_reason = "MAX_DOSE_NOT_AVAILABLE"
    trace.warnings.append("MAX_DOSE_NOT_AVAILABLE: source data has no maximum-dose field for this regimen")

    # Phase 8 — rounding: no governed rounding policy exists; exact result only.
    trace.rounding_status = "NOT_APPLIED"
    trace.exact_result_preserved = True

    trace.final_min_single_dose = single_min
    trace.final_max_single_dose = single_max
    trace.final_min_daily_dose = daily_min
    trace.final_max_daily_dose = daily_max
    trace.final_frequency = expr.frequency
    trace.final_unit = expr.numerator_unit
    trace.add_step(
        label="final",
        formula="summary",
        operands={},
        result={
            "single_dose": [single_min, single_max],
            "daily_dose": [daily_min, daily_max],
            "frequency": expr.frequency,
        },
        unit=expr.numerator_unit,
    )
    return trace


def apply_max_dose(trace: DoseCalculationTrace, source_max_daily_dose: Optional[float]) -> None:
    """Phase 7 — apply a maximum dose only if it is explicitly source-backed.

    Not called by `calculate()` automatically because assembled_regimens.sqlite
    carries no max-dose columns today; kept as a separate explicit step so a
    future source that *does* carry max-dose data can opt in without silently
    changing default behavior.
    """
    if source_max_daily_dose is None:
        trace.max_dose_reason = "MAX_DOSE_NOT_AVAILABLE"
        return
    if trace.final_max_daily_dose is not None and trace.final_max_daily_dose > source_max_daily_dose:
        trace.add_step(
            label="maximum dose",
            formula=f"min({trace.final_max_daily_dose}, {source_max_daily_dose})",
            operands={"raw": trace.final_max_daily_dose, "source_max": source_max_daily_dose},
            result=source_max_daily_dose, unit=trace.final_unit,
        )
        trace.final_max_daily_dose = source_max_daily_dose
        trace.max_dose_reason = "SOURCE_MAX_DAILY_DOSE"
    else:
        trace.max_dose_reason = "SOURCE_MAX_DAILY_DOSE"


def convert_to_volume(dose_mg: float, concentration_mg_per_ml: float) -> float:
    """Phase 9 — formulation conversion. Only called when the caller has an
    explicit, source-backed concentration; never inferred from a drug name."""
    if concentration_mg_per_ml <= 0:
        raise ValueError("concentration_mg_per_ml must be positive")
    return dose_mg / concentration_mg_per_ml
