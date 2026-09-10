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
        attach_crosswalk=False,
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
        index,
        diseases,
        output_path=out,
        run_source_gate=False,
        run_validate=False,
        attach_crosswalk=False,
    )
    # alphabetical by filename: a_disease.json before b_disease.json
    assert db["categories"][0]["file"] == "a_disease.json"
    assert db["categories"][1]["file"] == "b_disease.json"


def test_build_db_writes_utf8_no_bom_compact_no_trailing_newline(tmp_path):
    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"
    build_db(
        index,
        diseases,
        output_path=out,
        run_source_gate=False,
        run_validate=False,
        attach_crosswalk=False,
    )
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
        attach_crosswalk=False,
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
            attach_crosswalk=False,
        )


# ── КР corpus crosswalk attachment ───────────────────────────────────────────


def _write_crosswalk(tmp_path: Path, calculator: dict, index: dict) -> Path:
    """Build a real crosswalk artifact for a fixture database and commit it."""
    import json as _json

    from clinical_engine.crosswalk import build_crosswalk, write_crosswalk

    crosswalk = build_crosswalk(calculator, index)
    return write_crosswalk(crosswalk, tmp_path / "crosswalk.json")


def _fixture_documents(tmp_path: Path) -> tuple[dict, dict]:
    index_path, diseases_dir = _fixture(tmp_path)
    calculator = {
        "recommendations": [
            {"id": "disease_a", "name": "Disease A", "cr_id": "1_2", "mkb10": ["A01"]},
            {"id": "disease_b", "name": "Disease B", "cr_id": "2_2", "mkb10": ["B01"]},
        ]
    }
    diagnosis_index = {
        "meta": {"status": "AUTO_GENERATED_DRAFT"},
        "entries": [
            {
                "guideline_id": "10",
                "guideline_title": "Disease A guideline",
                "guideline_year": 2024,
                "guideline_revision_date": None,
                "diagnosis_name": "Disease A",
                "icd10_codes": ["A01"],
                "source_url": "",
            }
        ],
    }
    return calculator, diagnosis_index


def test_build_db_embeds_guideline_links_and_summary(tmp_path):
    from clinical_engine.crosswalk.builder import DEFAULT_DIAGNOSIS_INDEX

    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"
    calculator, diagnosis_index = _fixture_documents(tmp_path)
    index_path = tmp_path / "diagnosis_index.json"
    index_path.write_text(json.dumps(diagnosis_index, ensure_ascii=False), encoding="utf-8")
    crosswalk_path = _write_crosswalk(tmp_path, calculator, diagnosis_index)

    db = build_db(
        index,
        diseases,
        output_path=out,
        run_source_gate=False,
        run_validate=False,
        diagnosis_index_path=index_path,
        crosswalk_path=crosswalk_path,
    )

    by_id = {rec["id"]: rec for rec in db["recommendations"]}
    assert [link["guideline_id"] for link in by_id["disease_a"]["guideline_links"]] == ["10"]
    assert by_id["disease_a"]["guideline_links"][0]["codes"] == ["A01"]
    assert by_id["disease_b"]["guideline_links"] == []

    summary = db["meta"]["guideline_crosswalk"]
    assert summary["purpose"] == "NAVIGATION_ONLY"
    assert summary["links"] == 1
    assert summary["linked_diseases"] == 1
    assert summary["content_sha256"].startswith("sha256:")

    # the links really land on disk, not just in the returned object
    persisted = _load_json(out)
    assert persisted["recommendations"][0]["guideline_links"] == by_id["disease_a"]["guideline_links"]
    assert DEFAULT_DIAGNOSIS_INDEX.name == "diagnosis_index.json"


def test_build_db_refuses_to_embed_a_stale_crosswalk(tmp_path):
    import pytest

    from clinical_engine.crosswalk.builder import CrosswalkBuildError

    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"
    calculator, diagnosis_index = _fixture_documents(tmp_path)
    index_path = tmp_path / "diagnosis_index.json"
    index_path.write_text(json.dumps(diagnosis_index, ensure_ascii=False), encoding="utf-8")
    crosswalk_path = _write_crosswalk(tmp_path, calculator, diagnosis_index)
    # corrupt the committed artifact so it no longer matches its inputs
    crosswalk_path.write_text('{"meta": {"artifact_type": "CALCULATOR_GUIDELINE_CROSSWALK"}, "links": []}\n', encoding="utf-8")

    with pytest.raises(CrosswalkBuildError):
        build_db(
            index,
            diseases,
            output_path=out,
            run_source_gate=False,
            run_validate=False,
            diagnosis_index_path=index_path,
            crosswalk_path=crosswalk_path,
        )


def test_build_db_refuses_to_run_without_a_crosswalk(tmp_path):
    import pytest

    from clinical_engine.crosswalk.builder import CrosswalkBuildError

    index, diseases = _fixture(tmp_path)
    index_path = tmp_path / "diagnosis_index.json"
    index_path.write_text(json.dumps({"meta": {}, "entries": []}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CrosswalkBuildError):
        build_db(
            index,
            diseases,
            output_path=tmp_path / "out.json",
            run_source_gate=False,
            run_validate=False,
            diagnosis_index_path=index_path,
            crosswalk_path=tmp_path / "absent.json",
        )


def test_build_db_crosswalk_can_be_skipped_for_diagnostics(tmp_path):
    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"
    db = build_db(
        index,
        diseases,
        output_path=out,
        run_source_gate=False,
        run_validate=False,
        attach_crosswalk=False,
    )
    assert "guideline_links" not in db["recommendations"][0]
    assert "guideline_crosswalk" not in db["meta"]


def test_guideline_links_survive_a_second_build_unchanged(tmp_path):
    """Embedding links must not invalidate the crosswalk on the next build."""
    index, diseases = _fixture(tmp_path)
    out = tmp_path / "out.json"
    calculator, diagnosis_index = _fixture_documents(tmp_path)
    index_path = tmp_path / "diagnosis_index.json"
    index_path.write_text(json.dumps(diagnosis_index, ensure_ascii=False), encoding="utf-8")
    crosswalk_path = _write_crosswalk(tmp_path, calculator, diagnosis_index)

    kwargs = dict(
        run_source_gate=False,
        run_validate=False,
        diagnosis_index_path=index_path,
        crosswalk_path=crosswalk_path,
    )
    first = build_db(index, diseases, output_path=out, **kwargs)
    second = build_db(index, diseases, output_path=out, **kwargs)
    assert first == second
    assert first["meta"]["guideline_crosswalk"]["content_sha256"] == second["meta"]["guideline_crosswalk"]["content_sha256"]
