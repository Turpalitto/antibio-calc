from dose_verification_sandbox.parser import parse_dose_expression
from dose_verification_sandbox.calculator import calculate
from dose_verification_sandbox.verify import build_verification_result
from dose_verification_sandbox.models import NOT_AVAILABLE, BLOCKED


def test_blocked_arithmetic_never_reports_max_dose_or_rounding_as_pass():
    # regression: ambiguous-period case must not silently report max_dose=PASS
    regimen = {"regimen_id": "5574", "dose": 10.0, "unit": "mg/kg", "needs_review_reasons": ["unresolved_conflict"]}
    expr = parse_dose_expression(regimen["dose"], regimen["unit"], 1.0)
    trace = calculate(expr, weight_kg=18.0)
    assert trace.calculation_status == BLOCKED
    result = build_verification_result(regimen, expr, trace)
    assert result.max_dose == NOT_AVAILABLE
    assert result.rounding == NOT_AVAILABLE
    assert result.arithmetic == BLOCKED
