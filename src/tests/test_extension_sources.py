"""Tests for the extension-source classifier (DOSA klinrec -> candidate pool).

These tests assert the classification is a *source prover*: it never enables
calculation, never attests clinical approval, and classifies via the
regimen_type ratio (not keywords)."""

import json
from pathlib import Path

from src.pipeline.extraction import extension_sources as ec


def _g(code_version, name, mkb, regimens):
    return {
        "code_version": code_version,
        "guideline_name": name,
        "clinrec_id": code_version,
        "mkb": mkb,
        "regimens": [
            {"mkb": m, "regimen_type": rt}
            for (m, rt) in regimens
        ],
        "pdf_file": f"{code_version}.pdf",
        "pdf_sha256": "sha256:x",
        "publication_date": "2026-01-01",
    }


def _disease(id_, cr_id, mkb):
    return {"id": id_, "cr_id": cr_id, "mkb10": mkb}


def test_classify_regimen_ratio_therapeutic_when_no_prophylaxis():
    g = _g("900_1", "Title", ["A00.0"], [(["A00.0"], "first_line"), (["A00.0"], "alternative")])
    assert ec.classify_by_regimen_ratio(g) == ec.CLASS_THERAPEUTIC


def test_classify_regimen_ratio_primarily_prophylaxis():
    g = _g("901_1", "Title", ["A00.0"], [(["A00.0"], "prophylaxis"), (["A00.0"], "prophylaxis")])
    assert ec.classify_by_regimen_ratio(g) == ec.CLASS_PRIMARILY_PROPHYLAXIS


def test_classify_regimen_ratio_mixed():
    g = _g("902_1", "Title", ["A00.0"], [(["A00.0"], "prophylaxis"), (["A00.0"], "first_line"), (["A00.0"], "alternative")])
    assert ec.classify_by_regimen_ratio(g) == ec.CLASS_MIXED


def test_exact_mkb_overlap_marks_duplicate():
    kb = [_g("100_1", "Our cap adult", ["J18"], [(["J18"], "first_line")])]
    diseases = [_disease("cap_adult", "654_2", ["J13", "J18"])]
    idx = ec.build_disease_mkb_index(diseases)
    inv = ec.build_extension_inventory(kb, {"654_2"}, idx)
    assert inv["guidelines"][0]["overlaps_our_disease"] == ["cap_adult"]
    assert inv["guidelines"][0]["class"] == ec.CLASS_THERAPEUTIC


def test_disjoint_mkb_is_new_nosology():
    kb = [_g("910_1", "Diphtheria", ["A36"], [(["A36"], "first_line")])]
    diseases = [_disease("cap_adult", "654_2", ["J13", "J18"])]
    idx = ec.build_disease_mkb_index(diseases)
    inv = ec.build_extension_inventory(kb, {"654_2"}, idx)
    assert inv["guidelines"][0]["overlaps_our_disease"] == []
    rows = ec.flatten_nosologies(inv)
    assert rows[0]["cert_relation"] == ec.NEW_NOSOLOGY


def test_used_guideline_is_excluded():
    kb = [_g("654_2", "CAP adult", ["J18"], [(["J18"], "first_line")])]
    diseases = [_disease("cap_adult", "654_2", ["J13", "J18"])]
    idx = ec.build_disease_mkb_index(diseases)
    inv = ec.build_extension_inventory(kb, {"654_2"}, idx)
    assert inv["total"] == 0


def test_build_artifact_never_hints_unblock():
    kb = [
        _g("200_1", "Typhoid", ["A01.0"], [(["A01.0"], "first_line")]),
        _g("201_1", "ERYSIPELAS", ["A46"], [(["A46"], "alternative")]),
        _g("202_1", "Postop", ["A00.0"], [(["A00.0"], "prophylaxis")]),
    ]
    diseases = [_disease("cap_adult", "654_2", ["J13", "J18"])]
    db_path = Path(ec.__file__).parent.parent.parent.parent / "tmp" if False else None
    # Directly exercise via the public helpers (avoids writing a temp artifact).
    idx = ec.build_disease_mkb_index(diseases)
    inv = ec.build_extension_inventory(kb, {"654_2"}, idx)
    rows = ec.flatten_nosologies(inv)
    summary = ec.build_summary(rows)
    assert summary["new_nosology"] == 3
    assert summary["therapeutic"] == 2
    assert summary["primarily_prophylaxis"] == 1
    assert summary["therapeutic_new_nosology_count"] == 2
    # Source prover: no allowance to remove blockers / enable calculation.
    for r in rows:
        assert "unblock" not in str(r).lower()
