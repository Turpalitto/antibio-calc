from __future__ import annotations

import json

from src.pipeline.extraction.source_coverage import audit_source_coverage


def test_source_coverage_is_disease_level_and_fail_explicit(tmp_path):
    db = tmp_path / "db.json"
    specs = tmp_path / "specs"
    specs.mkdir()
    db.write_text(json.dumps({"recommendations": [
        {"id": "aom_child", "name": "AOM", "cr_id": "314", "cr_year": 2024},
        {"id": "aom_review", "name": "AOM pending", "cr_id": "314", "cr_year": 2024,
         "calculation_blocked": True, "calculation_block_reason": "candidate review pending"},
        {"id": "sinusitis_child", "name": "Sinusitis", "cr_id": "313_3", "cr_year": 2024,
         "calculation_blocked": True, "calculation_block_reason": "current PDF pending"},
        {"id": "other", "name": "Other", "cr_id": "999", "cr_year": 2024},
    ]}), encoding="utf-8")
    specs.joinpath("314.json").write_text(json.dumps({
        "guideline_id": "314", "rubricator_revision": "314",
        "expected_pdf_sha256": "sha256:" + "a" * 64,
    }), encoding="utf-8")
    report = audit_source_coverage(db, specs)
    assert report["disease_count"] == 4
    assert report["verified_spec_disease_count"] == 2
    assert report["missing_spec_disease_count"] == 2
    assert report["source_blocked_disease_count"] == 2
    assert report["unblocked_missing_spec_disease_count"] == 1
    assert [row["source_spec_status"] for row in report["rows"]] == [
        "VERIFIED_SPEC", "VERIFIED_SPEC_CALCULATION_BLOCKED", "SOURCE_BLOCKED", "MISSING_SPEC"
    ]
