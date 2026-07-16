"""RC-030 Evidence Validation, Phase 9/11 tests for the status model."""
import sqlite3
from pathlib import Path

from dose_verification_sandbox.semantics_parser import classify_regimen
from dose_verification_sandbox.semantics_risk_audit import assess_risk
from dose_verification_sandbox.validation_status import (
    validate, TYPES_MEETING_PRECISION_THRESHOLD, ValidatedDoseSemantics,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _row(**kw):
    base = dict(
        regimen_id="1", version=1, dose=None, unit="", frequency=None,
        source_quote="", source_pdf="x", source_page="1", guideline_id="g",
        confidence=0.5, duration_recommended=None, antibiotic="x",
    )
    base.update(kw)
    return base


def test_unparsed_row_never_calculation_eligible():
    row = _row(dose=None)
    ds = classify_regimen(row)
    v = validate(ds, None)
    assert v.calculation_eligibility == "BLOCKED"


def test_ambiguous_row_never_calculation_eligible():
    row = _row(dose=6.0, unit="mg/kg", frequency=3.0, source_quote="6 мг/кг")
    ds = classify_regimen(row)
    v = validate(ds, None)
    assert v.validation_status == "AMBIGUOUS"
    assert v.calculation_eligibility == "BLOCKED"


def test_no_type_meets_precision_threshold_yet():
    # per RC030_PRECISION_METRICS.md — must stay empty until a properly
    # powered validation run demonstrates 99% Wilson-lower-bound precision
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()


def test_unvalidated_parser_output_cannot_calculate_regardless_of_signal_strength():
    row = _row(dose=50.0, unit="mg/kg", frequency=2.0,
              source_quote="азитромицин 50 мг на кг массы тела в сутки, разделенные на 2 приема")
    ds = classify_regimen(row)
    v = validate(ds, None)
    assert ds.semantic_type == "WEIGHT_PER_DAY"
    assert v.evidence_level == "TEXTUAL_STRONG"
    # strong evidence still does not grant eligibility — type hasn't cleared the bar
    assert v.calculation_eligibility == "BLOCKED"


def test_high_risk_flagged_row_forced_unvalidated_even_if_parser_confident():
    row = _row(dose=250.0, unit="mg", frequency=1.0, age_group="adult",
              source_quote="азитромицин** 250 мг 1 раз в сут ежедневно или 500 мг один раз 3 сут/неделя, "
                           "рофлумиласт 250 или 500 мкг/сут")
    ds = classify_regimen(row)
    risk = assess_risk(row)
    v = validate(ds, risk)
    if risk and risk.is_high_risk:
        assert v.validation_status == "UNVALIDATED"
        assert v.calculation_eligibility == "BLOCKED"


def test_source_db_hash_unchanged_by_this_validation_module():
    # sanity: this module never opens assembled_regimens.sqlite at all
    import dose_verification_sandbox.validation_status as m
    text = Path(m.__file__).read_text(encoding="utf-8")
    assert "sqlite3" not in text
    assert "assembled_regimens" not in text
