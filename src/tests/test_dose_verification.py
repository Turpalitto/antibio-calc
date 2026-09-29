"""Tests for the dose source-verification harness (evidence only, never unblocks)."""
from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.extraction import dose_verification as dv


def _write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _kb_guideline(cv="314_3", regimens=None):
    return {
        "clinrec_id": 1, "guideline_name": "Отит", "code_version": cv,
        "pdf_file": "x.pdf", "pdf_sha256": "sha256:abc", "publication_date": "2024",
        "diagnosis": "Отит", "mkb": "H65.0", "regimens": regimens or [
            {"antibiotic": "Амоксициллин**", "dose": "50-60", "unit": "мг/кг",
             "age_group": "Дети", "route": "внутрь", "page_number": 24,
             "frequency": "в сутки в 2-3 приема", "source_quote": "q"},
        ],
    }


def _db_rec(regimens):
    return [{
        "id": "aom_child", "name": "Отит", "mkb10": ["H65.0"], "cr_id": "314_3",
        "cr_year": 2024, "antibiotics_indicated": True,
        "scenarios": [{
            "id": "s", "name": "s", "age_group": "child",
            "lines": [{
                "line_number": 1, "drugs": [{
                    "drug_ref": "amoxicillin", "route": ["per_os"],
                    "regimens": regimens,
                }],
            }],
        }],
    }]


def test_match_when_db_kg_in_kb_range(tmp_path):
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    _write(dbp, {"recommendations": _db_rec([{"age_group": "child", "dose_mg_kg_day": 60, "freq_per_day": 3}])})
    _write(kbp, [_kb_guideline()])
    rep = dv.verify(str(dbp), str(kbp))
    assert rep["summary"]["regimens_total"] == 1
    assert rep["summary"]["matched"] == 1
    assert rep["summary"]["mismatched"] == 0


def test_mismatch_when_db_kg_outside_kb_range(tmp_path):
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    _write(dbp, {"recommendations": _db_rec([{"age_group": "child", "dose_mg_kg_day": 200, "freq_per_day": 3}])})
    _write(kbp, [_kb_guideline()])
    rep = dv.verify(str(dbp), str(kbp))
    assert rep["summary"]["mismatched"] == 1


def test_no_kb_guideline_reported(tmp_path):
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    rec = _db_rec([{"age_group": "child", "dose_mg_kg_day": 60, "freq_per_day": 3}])[0]
    rec["cr_id"] = "999_9"
    _write(dbp, {"recommendations": [rec]})
    _write(kbp, [_kb_guideline()])
    rep = dv.verify(str(dbp), str(kbp))
    assert rep["summary"]["no_kb_guideline"] == 1
    assert rep["diseases"][0]["status"] == "NO_KB_GUIDELINE"


def test_uncomparable_when_no_kb_drug(tmp_path):
    """F-4: the old version wrote a `drug_ref_override` key that no code reads and
    then overwrote dbp, so the test asserted nothing about its own setup."""
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    rec = _db_rec([{"age_group": "child", "dose_mg_kg_day": 60, "freq_per_day": 3}])[0]
    rec["scenarios"][0]["lines"][0]["drugs"][0]["drug_ref"] = "ordnidazole"
    _write(dbp, {"recommendations": [rec]})
    _write(kbp, [_kb_guideline()])
    rep = dv.verify(str(dbp), str(kbp))
    assert rep["summary"]["uncomparable"] == 1
    assert rep["diseases"][0]["checks"][0]["reason"] == "no_kb_drug"


def test_artifact_never_hints_unblock(tmp_path):
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    _write(dbp, {"recommendations": _db_rec([{"age_group": "child", "dose_mg_kg_day": 60, "freq_per_day": 3}])})
    _write(kbp, [_kb_guideline()])
    rep = dv.verify(str(dbp), str(kbp))
    assert "APPROVED" not in json.dumps(rep)
    assert "CALCULATOR_BOUND_VERIFIED" not in json.dumps(rep)
    assert rep["note"]


# ---------------------------------------------------------------------------
# Tolerance must be scale-appropriate.  The old rule was `5% * |lo| + 1` on an
# ABSOLUTE mg scale, so a weight-based dose of 0.5 against a published 0.3 mg/kg
# -- a 67% relative error -- was reported as MATCH.
# ---------------------------------------------------------------------------

def test_h14_weight_dose_large_relative_error_is_not_a_match():
    assert dv._match_range(0.5, "0.3", weight_scale=True) == "MISMATCH"
    assert dv._match_range(0.3, "0.3", weight_scale=True) == "MATCH"
    assert dv._match_range(0.31, "0.3", weight_scale=True) == "MATCH"


def test_h14_absolute_dose_keeps_a_proportional_rounding_allowance():
    assert dv._match_range(501, "500", weight_scale=False) == "MATCH"
    assert dv._match_range(600, "500", weight_scale=False) == "MISMATCH"


def test_h14_small_absolute_doses_are_not_given_a_free_milligram():
    """A 0.3 -> 0.5 comparison on an absolute scale is still a 67% error."""
    assert dv._match_range(0.5, "0.3", weight_scale=False) == "MISMATCH"


def test_h14_small_relative_dose_tolerance_scales():
    # a 5% band on a weight scale, with no absolute floor
    assert dv._match_range(50, "50", weight_scale=True) == "MATCH"
    assert dv._match_range(52, "50", weight_scale=True) == "MATCH"
    assert dv._match_range(54, "50", weight_scale=True) == "MISMATCH"


def test_h14_end_to_end_small_kg_dose_is_mismatch(tmp_path):
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    kb = _kb_guideline(regimens=[{
        "antibiotic": "Амоксициллин**", "dose": "0,3", "unit": "мг/кг",
        "age_group": "Дети", "route": "внутрь", "page_number": 24,
        "frequency": "3 раза в день", "source_quote": "q",
    }])
    _write(kbp, [kb])
    _write(dbp, {"recommendations": _db_rec([
        {"age_group": "child", "dose_mg_kg_day": 0.5, "freq_per_day": 3}
    ])})
    rep = dv.verify(str(dbp), str(kbp))
    assert rep["summary"]["mismatched"] == 1, "a 67% weight-dose error was reported as MATCH"
    assert rep["summary"]["matched"] == 0


# ---------------------------------------------------------------------------
# M-11 -- all KB rows for a code_version must be considered
# ---------------------------------------------------------------------------

def test_m11_all_kb_rows_for_a_code_version_are_considered(tmp_path):
    """Only the FIRST guideline per code_version was kept before."""
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    first = _kb_guideline(regimens=[{
        "antibiotic": "Метронидазол**", "dose": "500", "unit": "мг",
        "age_group": "Дети", "route": "внутрь", "page_number": 24,
        "frequency": "3 раза в день", "source_quote": "q",
    }])
    second = _kb_guideline(regimens=[{
        "antibiotic": "Амоксициллин**", "dose": "50-60", "unit": "мг/кг",
        "age_group": "Дети", "route": "внутрь", "page_number": 25,
        "frequency": "в сутки в 2-3 приема", "source_quote": "q",
    }])
    assert first is not second
    _write(kbp, [first, second])
    _write(dbp, {"recommendations": _db_rec([
        {"age_group": "child", "dose_mg_kg_day": 60, "freq_per_day": 3}
    ])})
    rep = dv.verify(str(dbp), str(kbp))
    assert rep["summary"]["no_kb_guideline"] == 0
    assert rep["summary"]["matched"] == 1, "the SECOND row for this code_version was invisible"


# ---------------------------------------------------------------------------
# C-2 -- _dose_basis must be able to fire now that the basis is explicit
# ---------------------------------------------------------------------------

def test_c2_dose_basis_detects_consistency_of_a_per_dose_plus_daily_pair():
    assert dv._dose_basis({"single_dose_mg": 500, "dose_mg_day_fixed": 1500,
                          "freq_per_day": 3}) == "both_consistent"


def test_c2_dose_basis_flags_a_genuine_inconsistency():
    assert dv._dose_basis({"single_dose_mg": 500, "dose_mg_day_fixed": 1500,
                          "freq_per_day": 1}) == "inconsistent"


def test_c2_dose_basis_reports_per_dose_only():
    assert dv._dose_basis({"single_dose_mg": 1000, "freq_per_day": 3}) == "per_dose_only"
    assert dv._dose_basis({"single_dose_mg": 1000, "single_dose_mg_max": 2000,
                          "freq_per_day": 3}) == "per_dose_only"


def test_c2_dose_basis_distinguishes_weight_per_dose_from_weight_per_day():
    assert dv._dose_basis({"dose_mg_kg_per_dose": 7, "freq_per_day": 3}) == "weight_per_dose_only"
    assert dv._dose_basis({"dose_mg_kg_day": 30, "freq_per_day": 3}) == "weight_per_day_only"


def test_c2_dose_basis_accepts_a_range_consistent_pair():
    assert dv._dose_basis({"single_dose_mg": 500, "single_dose_mg_max": 1000,
                          "dose_mg_day_fixed": 1500, "dose_mg_day_fixed_max": 3000,
                          "freq_per_day": 3}) == "both_consistent"


# ---------------------------------------------------------------------------
# M-12 -- no machine-specific default paths
# ---------------------------------------------------------------------------

def test_m12_kb_default_is_not_a_machine_specific_temp_path():
    assert "/var/folders/" not in dv.KB_DEFAULT
    assert "/tmp/opencode" not in dv.KB_DEFAULT
    assert Path(dv.KB_DEFAULT).is_absolute()
    assert Path(dv.KB_DEFAULT).name == "knowledge_base.json"


def test_l8_clean_antibiotic_strips_markers():
    assert dv._clean_antibiotic("Амоксициллин** [1]") == "амоксициллин"
    assert dv._clean_antibiotic("#Цефтриаксон") == "цефтриаксон"
    assert "**" not in dv._clean_antibiotic("Амоксициллин**")


# ---------------------------------------------------------------------------
# L-7 -- dead code is gone
# ---------------------------------------------------------------------------

def test_l7_dead_helpers_removed():
    for name in ("_DRUG_TOKENS", "_drug_token", "_match_val"):
        assert not hasattr(dv, name), f"{name} is dead code that was never called"
