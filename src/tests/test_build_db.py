"""Tests for db/build_db.py (cross-platform Python port of build_db.ps1).

These verify the JSON assembly logic in isolation (no pwsh/node/network). The
source gate and validate steps are exercised only when explicitly enabled;
otherwise the unit tests confirm the assembly is faithful to the .ps1.
"""

from __future__ import annotations

import json
from pathlib import Path

from db.build_db import build_db, _load_json


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    index = {
        "meta": {
            "version": "0.5.0-draft",
            "schema_version": "1.1",
            "sources_base": "x",
            "load_order": "x",
        },
        "drugs_reference": {
            "_note": "excluded",
            "amoxicillin": {"inn": "amoxicillin", "forms": []},
        },
    }
    _write(tmp_path / "index.json", index)
    diseases = tmp_path / "diseases"
    _write(
        diseases / "a_disease.json",
        {
            "category": "A",
            "recommendations": [
                {
                    "id": "disease_a",
                    "mkb10": ["A01"],
                    "name": "Disease A",
                    "cr_id": "1_2",
                    "cr_year": 2024,
                    "antibiotics_indicated": True,
                    "scenarios": [],
                }
            ],
        },
    )
    _write(
        diseases / "b_disease.json",
        {
            "category": "B",
            "recommendations": [
                {
                    "id": "disease_b",
                    "mkb10": ["B01"],
                    "name": "Disease B",
                    "cr_id": "2_2",
                    "cr_year": 2023,
                    "antibiotics_indicated": True,
                    "scenarios": [],
                }
            ],
        },
    )
    return tmp_path / "index.json", diseases


def test_build_db_assembles_meta_drugs_categories_recommendations(tmp_path):
    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out" / "antibio_db.json"
    db = build_db(
        index,
        diseases,
        output_path=out,
        run_source_gate=False,
        run_validate=False,
    )
    assert db["meta"]["version"] == "0.5.0-draft"
    assert "amoxicillin" in db["drugs_reference"]
    # _note must not be treated as a drug in the reference produced
    assert "_note" in db["drugs_reference"]
    assert db["categories"] == [
        {"file": "a_disease.json", "category": "A", "count": 1},
        {"file": "b_disease.json", "category": "B", "count": 1},
    ]
    assert len(db["recommendations"]) == 2
    assert [r["id"] for r in db["recommendations"]] == ["disease_a", "disease_b"]
    assert _load_json(out)["recommendations"] == db["recommendations"]


def test_build_db_sorts_disease_files_by_filename(tmp_path):
    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"
    db = build_db(
        index, diseases, output_path=out, run_source_gate=False, run_validate=False
    )
    # alphabetical by filename: a_disease.json before b_disease.json
    assert db["categories"][0]["file"] == "a_disease.json"
    assert db["categories"][1]["file"] == "b_disease.json"


def test_build_db_writes_utf8_no_bom_compact_no_trailing_newline(tmp_path):
    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"
    build_db(index, diseases, output_path=out, run_source_gate=False, run_validate=False)
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # no BOM
    assert not raw.endswith(b"\n")  # no trailing newline
    # compact separators (no space after , or :)
    content = raw.decode("utf-8")
    assert ',"category"' in content
    assert '\n' not in content


def test_build_db_source_gate_runs_when_enabled(tmp_path, monkeypatch):
    from db import build_db as bd

    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"

    calls: list = []

    def fake_gate(output_path: Path, specs_dir: Path, python_exe: str | None) -> None:
        calls.append((str(output_path), str(specs_dir), python_exe))
        # simulate in-place mutation by the gate
        output_path.write_text(
            output_path.read_text(encoding="utf-8").replace(
                '"source_verification_status"', ""
            ),
            encoding="utf-8",
        ) if False else None
        db = json.loads(output_path.read_text(encoding="utf-8"))
        for r in db["recommendations"]:
            r["calculation_blocked"] = True
            r["source_verification_status"] = "SOURCE_SPEC_MISSING"
        output_path.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(bd, "_run_source_gate", fake_gate)
    monkeypatch.setattr(bd, "_run_validate", lambda op, ne: None)

    db = build_db(
        index,
        diseases,
        output_path=out,
        specs_dir=tmp_path / "specs",
        run_source_gate=True,
        run_validate=True,
    )
    assert len(calls) == 1
    # gate mutated all recommendations -> enforce blocked, source status set
    assert all(r.get("calculation_blocked") is True for r in db["recommendations"])
    assert all(
        r.get("source_verification_status") == "SOURCE_SPEC_MISSING"
        for r in db["recommendations"]
    )


def test_build_db_raises_on_gate_nonzero(tmp_path, monkeypatch):
    from db import build_db as bd

    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"
    monkeypatch.setattr(
        bd,
        "_run_source_gate",
        lambda op, specs_dir, python_exe: (_ for _ in ()).throw(
            RuntimeError("gate failed")
        ),
    )
    import pytest

    with pytest.raises(RuntimeError):
        build_db(
            index,
            diseases,
            output_path=out,
            specs_dir=tmp_path / "specs",
            run_source_gate=True,
            run_validate=False,
        )
