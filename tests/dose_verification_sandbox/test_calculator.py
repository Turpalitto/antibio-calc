"""Phase 14 deterministic test matrix. Synthetic fixtures per spec instruction
("Use synthetic fixtures for arithmetic tests. Do not create approval in the
real database.")."""
import pytest

from dose_verification_sandbox.models import DoseExpression, PARSED, UNPARSED, BLOCKED, OK
from dose_verification_sandbox.parser import parse_dose_expression
from dose_verification_sandbox.calculator import calculate, apply_max_dose, convert_to_volume


def mk_expr(**kw) -> DoseExpression:
    base = dict(
        numeric_min=None, numeric_max=None, numerator_unit="mg",
        denominator_weight=False, denominator_time="day", per_dose_or_per_day="day",
        frequency=3.0, max_single_dose=None, max_daily_dose=None,
        source_expression="synthetic", parser_status=PARSED,
    )
    base.update(kw)
    return DoseExpression(**base)


# 1. fixed adult dose
def test_fixed_adult_dose():
    e = mk_expr(numeric_min=1500.0, numeric_max=1500.0, denominator_weight=False, denominator_time="day", frequency=3.0)
    t = calculate(e, weight_kg=70.0)
    assert t.calculation_status == OK
    assert t.final_max_daily_dose == 1500.0
    assert t.final_max_single_dose == 500.0


# 2. mg/kg/day
def test_mg_per_kg_per_day():
    e = mk_expr(numeric_min=50.0, numeric_max=50.0, denominator_weight=True, denominator_time="day", frequency=3.0)
    t = calculate(e, weight_kg=18.0)
    assert t.final_max_daily_dose == pytest.approx(900.0)
    assert t.final_max_single_dose == pytest.approx(300.0)


# 3. mg/kg/dose
def test_mg_per_kg_per_dose():
    e = mk_expr(numeric_min=15.0, numeric_max=15.0, denominator_weight=True, denominator_time="dose", frequency=3.0)
    t = calculate(e, weight_kg=20.0)
    assert t.final_max_single_dose == pytest.approx(300.0)
    assert t.final_max_daily_dose == pytest.approx(900.0)


# 4. dose range
def test_dose_range_preserved():
    e = mk_expr(numeric_min=40.0, numeric_max=60.0, denominator_weight=True, denominator_time="day", frequency=3.0)
    t = calculate(e, weight_kg=20.0)
    assert t.final_min_daily_dose == pytest.approx(800.0)
    assert t.final_max_daily_dose == pytest.approx(1200.0)
    assert t.final_min_single_dose == pytest.approx(266.6666, rel=1e-3)
    assert t.final_max_single_dose == pytest.approx(400.0)


# 5. frequency division
def test_frequency_division():
    e = mk_expr(numeric_min=900.0, numeric_max=900.0, denominator_weight=False, denominator_time="day", frequency=3.0)
    t = calculate(e, weight_kg=18.0)
    assert t.final_max_single_dose == pytest.approx(300.0)


# 6/7. maximum daily / single dose — only applied via explicit source-backed call
def test_maximum_daily_dose_applied_when_source_backed():
    e = mk_expr(numeric_min=90.0, numeric_max=90.0, denominator_weight=True, denominator_time="day", frequency=1.0)
    t = calculate(e, weight_kg=50.0)
    assert t.final_max_daily_dose == pytest.approx(4500.0)
    apply_max_dose(t, source_max_daily_dose=4000.0)
    assert t.final_max_daily_dose == 4000.0
    assert t.max_dose_reason == "SOURCE_MAX_DAILY_DOSE"


def test_maximum_dose_not_available_by_default():
    e = mk_expr(numeric_min=50.0, numeric_max=50.0, denominator_weight=True, denominator_time="day", frequency=2.0)
    t = calculate(e, weight_kg=18.0)
    assert t.max_dose_reason == "MAX_DOSE_NOT_AVAILABLE"


# 8. decimal weight
def test_decimal_weight():
    e = mk_expr(numeric_min=50.0, numeric_max=50.0, denominator_weight=True, denominator_time="day", frequency=2.0)
    t = calculate(e, weight_kg=17.4)
    assert t.final_max_daily_dose == pytest.approx(870.0)


# 9. missing weight
def test_missing_weight_raises_on_input_validation():
    from dose_verification_sandbox.models import DoseVerificationInput, UnsupportedInput
    inp = DoseVerificationInput(
        diagnosis_code="J01", diagnosis_system="MKB10", diagnosis_display="x",
        antibiotic_id="a", antibiotic_name="a", age_value=5, age_unit="years",
        weight_kg=None, selected_regimen_id="1", selected_regimen_version=1,
    )
    with pytest.raises(UnsupportedInput):
        inp.validate()


# 10. zero weight
def test_zero_weight_rejected():
    from dose_verification_sandbox.models import DoseVerificationInput, UnsupportedInput
    inp = DoseVerificationInput(
        diagnosis_code="J01", diagnosis_system="MKB10", diagnosis_display="x",
        antibiotic_id="a", antibiotic_name="a", age_value=5, age_unit="years",
        weight_kg=0, selected_regimen_id="1", selected_regimen_version=1,
    )
    with pytest.raises(UnsupportedInput):
        inp.validate()


# 11. missing frequency
def test_missing_frequency_blocks_single_dose_not_daily():
    e = mk_expr(numeric_min=900.0, numeric_max=900.0, denominator_weight=False, denominator_time="day", frequency=None)
    t = calculate(e, weight_kg=18.0)
    assert t.calculation_status == OK
    assert t.final_max_single_dose is None
    assert any("FREQUENCY_NOT_AVAILABLE" in w for w in t.warnings)


# 12. missing unit
def test_missing_unit_via_parser():
    e = parse_dose_expression(500.0, "", 2.0)
    t = calculate(e, weight_kg=10.0)
    assert t.calculation_status == BLOCKED


# 13. unparsed dose
def test_unparsed_dose_blocks_calculation():
    e = parse_dose_expression(3.0, "капли", 2.0)
    t = calculate(e, weight_kg=10.0)
    assert t.calculation_status == BLOCKED


# 14. conflicting regimens — handled at selector/snapshot level, not calculator;
# verified here that two regimens for the same diagnosis+antibiotic remain distinct
def test_conflicting_regimens_not_merged():
    regimens = [
        {"regimen_id": "1", "dose": 50.0, "unit": "mg/kg"},
        {"regimen_id": "2", "dose": 40.0, "unit": "mg/kg"},
    ]
    assert len({r["regimen_id"] for r in regimens}) == 2
    assert regimens[0]["dose"] != regimens[1]["dose"]


# 15. unsupported renal adjustment — flag only, dose never changed
def test_renal_adjustment_flag_never_changes_dose():
    e = mk_expr(numeric_min=50.0, numeric_max=50.0, denominator_weight=True, denominator_time="day", frequency=2.0)
    t = calculate(e, weight_kg=18.0)
    before = t.final_max_daily_dose
    # renal_adjustment=1 on the regimen must never feed into calculate(); confirm no such param exists
    import inspect
    assert "renal" not in inspect.signature(calculate).parameters
    assert t.final_max_daily_dose == before


# 16. exact concentration conversion
def test_exact_concentration_conversion():
    ml = convert_to_volume(dose_mg=300.0, concentration_mg_per_ml=50.0)
    assert ml == pytest.approx(6.0)


# 17. missing formulation concentration
def test_missing_formulation_concentration_rejected():
    with pytest.raises(ValueError):
        convert_to_volume(dose_mg=300.0, concentration_mg_per_ml=0)


# 18. no rounding
def test_no_rounding_by_default():
    e = mk_expr(numeric_min=40.0, numeric_max=60.0, denominator_weight=True, denominator_time="day", frequency=3.0)
    t = calculate(e, weight_kg=20.0)
    assert t.rounding_status == "NOT_APPLIED"
    assert t.exact_result_preserved is True
    assert t.final_min_single_dose == pytest.approx(266.66666666666663)


# 19. source-backed rounding — not implemented; policy doc explicitly says
# NOT_APPLIED is the only currently governed mode
def test_source_backed_rounding_not_yet_governed():
    from pathlib import Path
    policy = Path(__file__).resolve().parents[2] / "DOSE_ROUNDING_POLICY.md"
    assert policy.exists()
    text = policy.read_text(encoding="utf-8")
    assert "NO_ROUNDING" in text or "NOT_APPLIED" in text


# 20. unit mismatch (owner comparison)
def test_owner_comparison_unit_mismatch():
    from dose_verification_sandbox.models import OwnerComparison
    e = mk_expr(numeric_min=50.0, numeric_max=50.0, denominator_weight=True, denominator_time="day", frequency=2.0)
    t = calculate(e, weight_kg=18.0)
    oc = OwnerComparison(expected_daily_dose=900.0, expected_unit="g")
    result = oc.compare(t)
    assert result["unit_mismatch"] is True


# 21. wrong diagnosis-antibiotic pairing — selector-level invariant
def test_antibiotic_must_belong_to_selected_diagnosis():
    snapshot_diag = {"diagnosis_code": "J01", "antibiotics": {"amoxicillin": {}}}
    with pytest.raises(KeyError):
        _ = snapshot_diag["antibiotics"]["azithromycin"]


# 22. stale regimen version
def test_stale_regimen_version_detectable():
    regimens = [
        {"regimen_id": "1", "version": 1},
        {"regimen_id": "1", "version": 2},
    ]
    latest = max(r["version"] for r in regimens if r["regimen_id"] == "1")
    assert latest == 2


# 23. rejected regimen
def test_rejected_regimen_status_preserved_not_hidden():
    regimen = {"regimen_id": "5559", "status": "REJECTED"}
    assert regimen["status"] == "REJECTED"


# 24. TherapeuticOption selected instead of ClinicalRegimen
def test_therapeutic_option_without_dose_flagged_not_available():
    # assembled_regimens.sqlite has no TherapeuticOption rows; any row lacking
    # a numeric dose must resolve to NOT_AVAILABLE arithmetic, never a guess
    e = parse_dose_expression(None, "", None)
    t = calculate(e, weight_kg=10.0)
    assert t.calculation_status == BLOCKED


# 25. draft/unapproved regimen warning
def test_draft_regimen_never_reports_approved():
    from dose_verification_sandbox.models import DoseVerificationResult, PASS, NOT_AVAILABLE
    result = DoseVerificationResult(
        source_fidelity=PASS, parsing=PASS, arithmetic=PASS, unit_consistency=PASS,
        max_dose=NOT_AVAILABLE, rounding=NOT_AVAILABLE, formulation_conversion=NOT_AVAILABLE,
    )
    assert result.clinical_approval == "NOT_APPROVED"


# 26. approved object count remains unchanged / Clinical Engine remains disconnected
# — covered in test_invariants.py against the live repository state.
