"""P5.4 tests — field normalization safety rules + quality improvement pass."""
import os

import pytest

from clinical_engine.regimen.field_normalization import (
    canonicalize_unit, normalize_frequency_display, recover_route_from_quote,
)
from clinical_engine.regimen.clinical_regimen import UNKNOWN, ClinicalRegimen, FieldProvenance, LifecycleState
from clinical_engine.regimen.quality_improvement import apply_quality_improvements
from clinical_engine.regimen.assembly_engine import AssemblyResult, AssemblyMetrics

NR = r"C:\clinrec_downloader\normalized_regimens.sqlite"
KB = "kb_p44.db"


# --- route recovery: only ever recovers from LITERAL text, never invents ---
def test_recovers_single_unambiguous_route():
    out = recover_route_from_quote("Тедизолид назначают внутривенно 200 мг 1 раз в сутки.", "r1", "x.pdf", "1")
    assert out.recovered and out.value == "intravenous"
    assert out.provenance is not None
    assert out.provenance.source_store == "normalized_regimens+text_normalization"


def test_does_not_guess_when_no_route_keyword_present():
    out = recover_route_from_quote("Амоксициллин 500 мг 2 раза в сутки.", "r2", "x.pdf", "1")
    assert not out.recovered
    assert out.reason == "no_route_keyword_in_source_quote"


def test_does_not_guess_when_ambiguous_multiple_routes():
    out = recover_route_from_quote(
        "Азитромицин 1 г внутривенно или внутрь, затем 0,5 г в день.", "r3", "x.pdf", "1")
    assert not out.recovered
    assert "ambiguous" in out.reason


def test_unit_canonicalization_never_changes_value_semantics():
    assert canonicalize_unit("г") == "g"
    assert canonicalize_unit("мг") == "mg"
    assert canonicalize_unit("unknown_unit") == "unknown_unit"  # untouched if not in the safe dictionary


def test_frequency_display_does_not_alter_underlying_number():
    assert normalize_frequency_display(2.0) == "2x/day"
    assert normalize_frequency_display(None) == UNKNOWN
    # sub-daily frequency represented as a period, not rounded to a different daily value
    assert "days" in normalize_frequency_display(1 / 3)


# --- quality improvement pass: additive over unchanged P5.3 regimens ---
def _reg(**kw):
    base = dict(
        regimen_id="r1", version=1, status=LifecycleState.ASSEMBLED, diagnosis="d", icd_mkb="A01.0",
        age_group="adult", weight_range=UNKNOWN, pregnancy=None, renal_adjustment=False,
        therapy_line="first", antibiotic="tedizolid", dose=200.0, unit="mg", frequency=1.0,
        duration_recommended=6.0, duration_min=None, duration_max=None, route="unknown",
        guideline_id="1", evidence_level=UNKNOWN, contraindications=(),
        field_provenance=tuple((f, FieldProvenance("r1", "x.pdf", "p1", "normalized_regimens"))
                               for f in ("antibiotic", "dose")),
        source_pdf="x.pdf", source_page="1",
        source_quote="Тедизолид назначают внутривенно 200 мг 1 раз в сутки в течение 6 дней.",
        validation_verdict="REJECT",
    )
    base.update(kw)
    return ClinicalRegimen(**base)


def test_quality_pass_recovers_route_and_flips_reject_to_pass():
    res = AssemblyResult(regimens=[_reg()], conflicts=[], metrics=AssemblyMetrics())
    qi = apply_quality_improvements(res)
    assert qi.before_verdicts["REJECT"] == 1
    r = qi.regimens[0]
    assert r.route == "intravenous"
    assert r.provenance_for("route") is not None
    assert qi.after_verdicts["PASS"] == 1
    assert qi.metrics.route_recovered == 1


def test_quality_pass_never_touches_ambiguous_or_absent_route():
    # ambiguous route -> stays unset, verdict unchanged (still missing route -> still REJECT-eligible)
    r = _reg(source_quote="Азитромицин 1 г внутривенно или внутрь.")
    res = AssemblyResult(regimens=[r], conflicts=[], metrics=AssemblyMetrics())
    qi = apply_quality_improvements(res)
    assert qi.regimens[0].route == "unknown"
    assert qi.metrics.route_ambiguous_skipped == 1


def test_quality_pass_never_fabricates_dose():
    # a regimen with NO dose at all must remain REJECT-eligible; quality pass only touches route
    r = _reg(dose=None, route="unknown", source_quote="Макролиды могут быть использованы.")
    res = AssemblyResult(regimens=[r], conflicts=[], metrics=AssemblyMetrics())
    qi = apply_quality_improvements(res)
    assert qi.regimens[0].dose is None  # never fabricated
    assert qi.after_verdicts["REJECT"] == 1


# --- real full-corpus run (skips if data absent) ---
def test_real_full_run_reduces_reject_without_hiding_clinical_gaps():
    if not os.path.exists(NR):
        pytest.skip("normalized_regimens.sqlite not available")
    from clinical_engine.regimen.assembly_engine import RegimenAssemblyEngine
    res = RegimenAssemblyEngine(NR, KB).assemble()
    qi = apply_quality_improvements(res)
    assert qi.before_verdicts["REJECT"] == 1132  # matches P5.3 baseline exactly
    assert qi.after_verdicts["REJECT"] < qi.before_verdicts["REJECT"]  # improved
    assert qi.after_verdicts["REJECT"] >= qi.before_verdicts["REJECT"] - 300  # bounded (only ~296 recoverable)
    assert qi.metrics.route_recovered > 0
