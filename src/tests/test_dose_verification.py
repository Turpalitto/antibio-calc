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
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    _write(dbp, {"recommendations": _db_rec([{"age_group": "child", "dose_mg_kg_day": 60, "freq_per_day": 3,
                                             "drug_ref_override": "vancomycin"}])})
    # different drug not in KB
    kb = _kb_guideline()
    _write(kbp, [kb])
    # use a bespoke rec with unusual ref
    rec = _db_rec([{"age_group": "child", "dose_mg_kg_day": 60, "freq_per_day": 3}])[0]
    rec["scenarios"][0]["lines"][0]["drugs"][0]["drug_ref"] = "ordnidazole"
    _write(dbp, {"recommendations": [rec]})
    rep = dv.verify(str(dbp), str(kbp))
    assert rep["summary"]["uncomparable"] == 1


def test_artifact_never_hints_unblock(tmp_path):
    dbp = tmp_path / "db.json"; kbp = tmp_path / "kb.json"
    _write(dbp, {"recommendations": _db_rec([{"age_group": "child", "dose_mg_kg_day": 60, "freq_per_day": 3}])})
    _write(kbp, [_kb_guideline()])
    rep = dv.verify(str(dbp), str(kbp))
    assert "APPROVED" not in json.dumps(rep)
    assert "CALCULATOR_BOUND_VERIFIED" not in json.dumps(rep)
    assert rep["note"]
