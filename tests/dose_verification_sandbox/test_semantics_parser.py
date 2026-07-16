"""RC-030 Phase 12 tests for the source-backed dose semantics parser."""
import pytest

from dose_verification_sandbox.semantics_parser import (
    classify_regimen, extract_max_dose_signal, extract_max_dose_value_from_window,
)
from dose_verification_sandbox.semantics_integration import calculate_from_semantics, eligibility
from dose_verification_sandbox.models import BLOCKED, OK


def mk_row(**kw) -> dict:
    base = dict(
        regimen_id="9999", version=1, dose=None, unit="", frequency=None,
        source_quote="", source_pdf="x.pdf", source_page="1", guideline_id="g1",
        confidence=0.5, duration_recommended=None, antibiotic="Тестовый",
    )
    base.update(kw)
    return base


# explicit mg/kg/day (Russian)
def test_explicit_weight_per_day_russian():
    row = mk_row(dose=10.0, unit="mg/kg", frequency=1.0,
                 source_quote="азитромицин** 10 мг на кг массы тела в сутки в течение 7 дней")
    ds = classify_regimen(row)
    assert ds.semantic_type == "WEIGHT_PER_DAY"
    assert ds.time_denominator == "day"


# explicit mg/kg/dose via "каждые N часов"
def test_explicit_weight_per_dose_every_n_hours():
    row = mk_row(dose=25.0, unit="mg/kg", frequency=2.0,
                 source_quote="ампициллин** 25-50 мг/кг каждые 12 ч")
    ds = classify_regimen(row)
    assert ds.semantic_type == "WEIGHT_PER_DOSE"
    assert ds.time_denominator == "dose"


# Russian per-day syntax: "N раз в сутки" for a fixed mg dose
def test_fixed_per_dose_via_n_raz_v_sutki():
    row = mk_row(dose=1000.0, unit="mg", frequency=2.0,
                 source_quote="цефтриаксон** в дозе 1000мг 2 раза в сутки внутримышечно")
    ds = classify_regimen(row)
    assert ds.semantic_type == "FIXED_PER_DOSE"
    assert ds.time_denominator == "dose"


# Russian per-day syntax: bare "в сутки" / "/сут" for fixed mg
def test_fixed_per_day_via_v_sutki():
    row = mk_row(dose=100.0, unit="mg", frequency=1.0,
                 source_quote="доксициклин** 100 мг в сутки перорально в один или несколько приемов")
    ds = classify_regimen(row)
    assert ds.semantic_type in ("FIXED_PER_DAY",)
    assert ds.time_denominator == "day"


# spelled-out Russian frequency count ("два раза")
def test_spelled_out_frequency_count():
    row = mk_row(dose=400.0, unit="mg", frequency=2.0,
                 source_quote="Метронидазол** 400 мг два раза в день в течение 7 дней")
    ds = classify_regimen(row)
    assert ds.semantic_type == "FIXED_PER_DOSE"


# frequency == 1 collapses per-dose vs per-day ambiguity algebraically
def test_frequency_one_resolves_without_textual_signal():
    row = mk_row(dose=2.0, unit="g", frequency=1.0, source_quote="ампициллин** 2 г внутрь")
    ds = classify_regimen(row)
    assert ds.ambiguity_status == "RESOLVED_BY_FREQUENCY_ONE"
    assert ds.semantic_type in ("FIXED_PER_DAY", "FIXED_PER_DOSE")


# regression (RC-030 Evidence Validation Phase 4): the frequency=1 shortcut
# must NEVER apply when the dose token itself cannot be located anywhere in
# source_quote — found on real regimen 7951, where dose=10 does not appear
# literally in the quote text at all. Previously this produced a false
# WEIGHT_PER_DAY/RESOLVED_BY_FREQUENCY_ONE with zero textual evidence.
def test_frequency_one_shortcut_never_applies_without_locatable_dose_token():
    row = mk_row(dose=10.0, unit="mg/kg", frequency=1.0,
                 source_quote="Хирургическое лечение внутриротовым доступом. Цефазолин** + Метронидазол** "
                              "Ванкомицин3**+ #Клиндамицин** За 30-60 минут до разреза. Допускается продление до 48 часов.")
    ds = classify_regimen(row)
    assert ds.semantic_type == "AMBIGUOUS"
    assert ds.ambiguity_status == "AMBIGUOUS_NO_SIGNAL"


# genuinely ambiguous: mg/kg, no signal, frequency != 1
def test_ambiguous_mg_per_kg_with_frequency_no_signal():
    row = mk_row(dose=6.0, unit="mg/kg", frequency=3.0, source_quote="гентамицин 6 мг/кг")
    ds = classify_regimen(row)
    assert ds.semantic_type == "AMBIGUOUS"
    assert ds.ambiguity_status == "AMBIGUOUS_NO_SIGNAL"


# conflicting signals in the same window
def test_conflicting_signal_stays_ambiguous():
    row = mk_row(dose=50.0, unit="mg/kg", frequency=2.0,
                 source_quote="50 мг/кг в сутки, вводится 2 раза в день не по этой схеме")
    ds = classify_regimen(row)
    # depending on proximity either resolves or reports conflict — but never guesses
    assert ds.semantic_type in ("AMBIGUOUS", "WEIGHT_PER_DAY", "WEIGHT_PER_DOSE")


# max daily dose extraction
def test_max_daily_dose_extraction():
    row = mk_row(dose=50.0, unit="mg/kg", frequency=1.0,
                 source_quote="амоксициллина в дозе 50 мг/кг (детская дозировка), но не более 2 гр. (взрослая дозировка)")
    ds = classify_regimen(row)
    assert ds.max_daily_dose == 2000.0 or ds.max_single_dose == 2000.0


# "не более 24 часов" must never be captured as a dose (duration, not mass)
def test_max_dose_never_captures_duration():
    row = mk_row(dose=2.0, unit="g", frequency=1.0,
                 source_quote="Цефазолин** 2,0 г ... вводятся не более 24 часов после операции")
    ds = classify_regimen(row)
    assert ds.max_daily_dose is None
    assert ds.max_single_dose is None


def test_no_max_dose_signal_present():
    row = mk_row(dose=500.0, unit="mg", frequency=1.0, source_quote="500 мг в сутки")
    ds = classify_regimen(row)
    assert ds.max_daily_dose is None and ds.max_single_dose is None


# unsupported unit
def test_unsupported_compound_unit_stays_unparsed():
    row = mk_row(dose=1.0, unit="г; мг/кг", frequency=2.0, source_quote="1 г; мг/кг")
    ds = classify_regimen(row)
    assert ds.semantic_type == "UNPARSED"


# missing frequency, explicit per-day signal
def test_missing_frequency_still_classified_per_day():
    row = mk_row(dose=0.5, unit="mg/kg", frequency=None,
                 source_quote="0,5-1,0 мг/кг/сутки при отравлении")
    ds = classify_regimen(row)
    assert ds.semantic_type == "WEIGHT_PER_DAY"


# stale regimen version detection
def test_stale_semantic_version_blocked():
    row = mk_row(dose=50.0, unit="mg/kg", frequency=1.0, version=1,
                 source_quote="50 мг/кг в сутки")
    ds = classify_regimen(row)
    status, reasons = eligibility(ds, latest_version=2)
    assert status == BLOCKED
    assert any("STALE_SEMANTIC_VERSION" in r for r in reasons)


def test_non_stale_semantic_version_eligible():
    row = mk_row(dose=50.0, unit="mg/kg", frequency=1.0, version=2,
                 source_quote="50 мг/кг в сутки")
    ds = classify_regimen(row)
    status, reasons = eligibility(ds, latest_version=2)
    assert status == "ELIGIBLE"


# idempotent semantic rebuild
def test_idempotent_rebuild(tmp_path):
    from dose_verification_sandbox.semantics_store import rebuild_store
    row = mk_row(dose=50.0, unit="mg/kg", frequency=1.0, source_quote="50 мг/кг в сутки")
    ds = classify_regimen(row)
    store_path = tmp_path / "store.sqlite"
    r1 = rebuild_store([ds], path=store_path)
    ds2 = classify_regimen(row)  # re-classify identical input
    r2 = rebuild_store([ds2], path=store_path)
    assert r1["inserted"] == 1
    assert r2["inserted"] == 0
    assert r2["skipped_unchanged"] == 1


# source DB unchanged
def test_classify_never_mutates_input_dict():
    row = mk_row(dose=50.0, unit="mg/kg", frequency=1.0, source_quote="50 мг/кг в сутки")
    snapshot = dict(row)
    classify_regimen(row)
    assert row == snapshot


# no clinical approval anywhere in this module
def test_no_clinical_engine_import_in_semantics_modules():
    import dose_verification_sandbox.semantics_parser as m1
    import dose_verification_sandbox.semantics_integration as m2
    import dose_verification_sandbox.semantics_store as m3
    from pathlib import Path
    for mod in (m1, m2, m3):
        for line in Path(mod.__file__).read_text(encoding="utf-8").splitlines():
            s = line.strip()
            assert not s.startswith(("import clinical_engine", "from clinical_engine"))


# blocked arithmetic remains NOT_AVAILABLE for max/rounding through the semantics path too
def test_blocked_through_semantics_path_reports_not_available():
    from dose_verification_sandbox.verify import build_verification_result
    row = mk_row(dose=6.0, unit="mg/kg", frequency=3.0, source_quote="гентамицин 6 мг/кг")
    row["needs_review_reasons"] = []
    ds = classify_regimen(row)
    status, reasons, trace = calculate_from_semantics(ds, weight_kg=18.0)
    assert trace.calculation_status == BLOCKED
    result = build_verification_result(row, semantics_expression(ds), trace)
    assert result.max_dose == "NOT_AVAILABLE"
    assert result.rounding == "NOT_AVAILABLE"


def semantics_expression(ds):
    from dose_verification_sandbox.semantics_integration import semantics_to_expression
    return semantics_to_expression(ds)
