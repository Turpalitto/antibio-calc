"""RC-030 deterministic repair — regression tests (Phases 2-11).

Every test asserts fail-closed behavior. None of these makes any regimen
calculation-eligible (TYPES_MEETING_PRECISION_THRESHOLD stays empty).
"""
import pytest

from dose_verification_sandbox.semantics_parser import classify_regimen
from dose_verification_sandbox.validation_status import validate, TYPES_MEETING_PRECISION_THRESHOLD
from dose_verification_sandbox.semantics_risk_audit import assess_risk


def mk(dose, unit, freq, quote, **kw):
    r = {"regimen_id": "T", "version": 1, "dose": dose, "unit": unit, "frequency": freq,
         "source_quote": quote, "antibiotic": "x", "diagnosis": "x"}
    r.update(kw)
    return r


# ---- Phase 2: frequency==1 no longer establishes semantics ----
def test_freq1_markerless_weight_stays_ambiguous():
    ds = classify_regimen(mk(50.0, "mg/kg", 1.0, "цефуроксим** 50 мг/кг"))
    assert ds.semantic_type == "AMBIGUOUS"
    assert "EXPLICIT_DOSE_BASIS_MISSING" in ds.schedule_risk_flags

def test_freq1_markerless_fixed_stays_ambiguous():
    ds = classify_regimen(mk(1.5, "g", 1.0, "цефуроксим** 1,5 г"))
    assert ds.semantic_type == "AMBIGUOUS"

def test_regimen_6657_calibration_ambiguous_blocked():
    ds = classify_regimen(mk(50.0, "mg/kg", 1.0, "цефуроксим** 50 мг/кг"))
    assert ds.semantic_type == "AMBIGUOUS"
    assert "EXPLICIT_DOSE_BASIS_MISSING" in ds.schedule_risk_flags
    assert validate(ds, assess_risk(mk(50.0, "mg/kg", 1.0, "цефуроксим** 50 мг/кг"))).calculation_eligibility == "BLOCKED"


# ---- explicit markers still resolve ----
def test_explicit_sut_per_day():
    assert classify_regimen(mk(8.0, "mg/kg", 1.0, "8 мг/кг/сут в 1 прием")).semantic_type == "WEIGHT_PER_DAY"

def test_explicit_sutki_per_day():
    assert classify_regimen(mk(40.0, "mg/kg", 2.0, "40 мг/кг/сутки в 2 приема")).semantic_type == "WEIGHT_PER_DAY"

def test_explicit_na_vvedenie_per_dose():
    assert classify_regimen(mk(25.0, "mg/kg", 2.0, "25 мг/кг на введение каждые 12 часов")).semantic_type == "WEIGHT_PER_DOSE"


# ---- Phase 3: однократно ----
def test_odnokratno_fixed_single():
    ds = classify_regimen(mk(2.0, "g", 1.0, "тинидазол 2,0 г однократно"))
    assert ds.semantic_type == "FIXED_PER_DOSE"
    assert ds.schedule_period == "SINGLE"

def test_odnokratno_weight_per_dose():
    ds = classify_regimen(mk(10.0, "mg/kg", 1.0, "клиндамицин в разовой дозе 10 мг/кг однократно"))
    assert ds.semantic_type == "WEIGHT_PER_DOSE"


# ---- Phase 4: token normalization ----
def test_r_sut_recognized_per_dose():
    assert classify_regimen(mk(500.0, "mg", 2.0, "ципрофлоксацин 500 мг 2 р/сут")).semantic_type == "FIXED_PER_DOSE"

def test_dvazhdy_recognized_per_dose():
    assert classify_regimen(mk(100.0, "mg", 2.0, "доксициклин 100 мг дважды в день")).semantic_type == "FIXED_PER_DOSE"

def test_trizhdy_recognized_per_dose():
    assert classify_regimen(mk(500.0, "mg", 3.0, "амоксициллин 500 мг трижды в день")).semantic_type == "FIXED_PER_DOSE"


# ---- Phase 5: schedule guards ----
def test_weekly_schedule_flagged_and_blocked():
    ds = classify_regimen(mk(10.0, "mg/kg", 1.0, "азитромицин 10 мг/кг/сут 1 раз в день 3 раза в неделю"))
    assert ds.schedule_period == "WEEKLY"
    assert "WEEKLY_SCHEDULE_UNSUPPORTED" in ds.schedule_risk_flags
    assert validate(ds, assess_risk(mk(10.0, "mg/kg", 1.0, "азитромицин 10 мг/кг/сут 1 раз в день 3 раза в неделю"))).calculation_eligibility == "BLOCKED"

def test_every_other_day_flagged():
    ds = classify_regimen(mk(5.0, "mg/kg", 1.0, "препарат 5 мг/кг/сут через день"))
    assert ds.schedule_period == "EVERY_OTHER_DAY"
    assert "NON_DAILY_SCHEDULE" in ds.schedule_risk_flags

def test_every_n_hours_interval_informational():
    ds = classify_regimen(mk(10.0, "mg/kg", 2.0, "ванкомицин 10 мг/кг каждые 12 часов"))
    assert ds.interval_hours == 12.0
    assert ds.administrations_per_day == 2.0
    assert ds.semantic_type == "WEIGHT_PER_DOSE"

def test_sub_daily_frequency_flagged():
    ds = classify_regimen(mk(90.0, "mg/kg", 0.4286, "препарат 90 мг/кг/сут"))
    assert "SUB_DAILY_FREQUENCY" in ds.schedule_risk_flags


# ---- Phase 8: loading/maintenance ----
def test_loading_maintenance_unresolved():
    ds = classify_regimen(mk(15.0, "mg/kg", 1.0,
        "нагрузочная доза 15 мг/кг, затем поддерживающая доза 10 мг/кг каждые 8 часов"))
    assert "LOADING_MAINTENANCE_UNRESOLVED" in ds.schedule_risk_flags


# ---- Phase 11: range-loss guard ----
def test_true_range_collapsed_flagged():
    ds = classify_regimen(mk(20.0, "mg/kg", 2.0, "20-50 мг/кг/сут в 2 приема"))
    assert ds.range_collapsed_upstream is True
    assert ds.range_min_source == 20.0 and ds.range_max_source == 50.0
    assert "RANGE_VALUE_COLLAPSED_UPSTREAM" in ds.schedule_risk_flags

def test_en_dash_range():
    ds = classify_regimen(mk(500.0, "mg", 3.0, "амоксициллин 500–1000 мг 3 раза в сутки"))
    assert ds.range_max_source == 1000.0

def test_ot_do_range():
    ds = classify_regimen(mk(20.0, "mg/kg", 1.0, "от 20 до 80 мг/кг/сут"))
    assert ds.range_min_source == 20.0 and ds.range_max_source == 80.0

def test_age_range_not_dose_range():
    # "2-5 лет" must not be captured as a dose range
    ds = classify_regimen(mk(250.0, "mg", 2.0, "детям 2-5 лет 250 мг 2 раза в сутки"))
    assert ds.range_collapsed_upstream is False

def test_duration_range_not_dose_range():
    ds = classify_regimen(mk(500.0, "mg", 2.0, "500 мг 2 раза в сутки в течение 7-10 дней"))
    assert ds.range_collapsed_upstream is False

def test_alternatives_not_range():
    # "или" alternatives are not a numeric range
    ds = classify_regimen(mk(500.0, "mg", 3.0, "500 мг 3 раза в сутки или 875 мг 2 раза в сутки"))
    assert ds.range_collapsed_upstream is False


# ---- global safety ----
def test_no_repair_activates_calculation():
    cases = [
        mk(50.0, "mg/kg", 1.0, "цефуроксим** 50 мг/кг"),
        mk(2.0, "g", 1.0, "тинидазол 2,0 г однократно"),
        mk(20.0, "mg/kg", 2.0, "20-50 мг/кг/сут в 2 приема"),
        mk(10.0, "mg/kg", 1.0, "азитромицин 10 мг/кг/сут 3 раза в неделю"),
    ]
    for c in cases:
        assert validate(classify_regimen(c), assess_risk(c)).calculation_eligibility == "BLOCKED"
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()

# Note: normalizer-specific range-preservation tests (DoseNormalizer.parse())
# live in medical_normalizer/tests/test_drug_parser.py, not here — this file
# is C1 (RC-030 sandbox parser); the normalizer is C2. Keeping them separate
# means each commit's tests pass independently of the other.
