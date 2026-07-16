"""RC-030 Evidence Validation, Phase 6 regression: frequency < 1/day (e.g.
"3 times a week" stored as 3/7) must never be divided into a daily dose to
derive a "single dose" — that produces a single-dose value larger than the
daily total, a mathematical impossibility. Found on real regimen 5376."""
import pytest

from dose_verification_sandbox.models import DoseExpression, PARSED, BLOCKED
from dose_verification_sandbox.calculator import calculate


def test_sub_daily_frequency_blocks_calculation():
    expr = DoseExpression(
        numeric_min=5.0, numeric_max=5.0, numerator_unit="mg",
        denominator_weight=True, denominator_time="day", per_dose_or_per_day="day",
        frequency=3 / 7, max_single_dose=None, max_daily_dose=None,
        source_expression="5 mg/kg/day, 3x/week", parser_status=PARSED,
    )
    trace = calculate(expr, weight_kg=18.0)
    assert trace.calculation_status == BLOCKED
    assert any("SUB_DAILY_FREQUENCY" in w for w in trace.warnings)
    # the bug this guards against: single dose must never exceed daily dose
    assert trace.final_min_single_dose is None


def test_daily_frequency_of_exactly_one_still_works():
    expr = DoseExpression(
        numeric_min=50.0, numeric_max=50.0, numerator_unit="mg",
        denominator_weight=True, denominator_time="day", per_dose_or_per_day="day",
        frequency=1.0, max_single_dose=None, max_daily_dose=None,
        source_expression="50 mg/kg/day", parser_status=PARSED,
    )
    trace = calculate(expr, weight_kg=18.0)
    assert trace.calculation_status == "OK"
    assert trace.final_min_single_dose == pytest.approx(900.0)


def test_normal_multi_daily_frequency_still_works():
    expr = DoseExpression(
        numeric_min=50.0, numeric_max=50.0, numerator_unit="mg",
        denominator_weight=True, denominator_time="day", per_dose_or_per_day="day",
        frequency=3.0, max_single_dose=None, max_daily_dose=None,
        source_expression="50 mg/kg/day, 3x/day", parser_status=PARSED,
    )
    trace = calculate(expr, weight_kg=18.0)
    assert trace.calculation_status == "OK"
    assert trace.final_min_single_dose == pytest.approx(300.0)
