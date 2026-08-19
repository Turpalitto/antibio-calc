from __future__ import annotations

import json

from src.pipeline.extraction.source_inventory import build_source_inventory


def test_inventory_uses_exact_revision_and_latest_numeric_code(tmp_path):
    db = tmp_path / "db.json"
    metadata = tmp_path / "clinrecs.json"
    corpus = tmp_path / "pdfs"
    corpus.mkdir()
    db.write_text(json.dumps({"recommendations": [
        {"id": "exact", "name": "Exact", "cr_id": "10_2", "cr_year": 2024},
        {"id": "latest", "name": "Latest", "cr_id": "20", "cr_year": 2023},
        {"id": "missing", "name": "Missing", "cr_id": "—", "cr_year": 2021},
    ]}), encoding="utf-8")
    metadata.write_text(json.dumps([
        {"Id": 1, "Name": "Exact", "Code": 10, "Version": 1, "CodeVersion": "10_1"},
        {"Id": 2, "Name": "Exact", "Code": 10, "Version": 2, "CodeVersion": "10_2"},
        {"Id": 3, "Name": "Latest old", "Code": 20, "Version": 1, "CodeVersion": "20_1"},
        {"Id": 4, "Name": "Latest", "Code": 20, "Version": 3, "CodeVersion": "20_3"},
    ]), encoding="utf-8")
    report = build_source_inventory(db, metadata, [corpus])
    assert report["disease_count"] == 3
    assert report["declared_cr_id_count"] == 2
    assert report["metadata_match_count"] == 2
    assert report["rows"][0]["latest_local_metadata"]["CodeVersion"] == "10_2"
    assert report["rows"][1]["latest_local_metadata"]["CodeVersion"] == "20_3"
    assert report["rows"][2]["metadata_match_basis"] == "NO_DECLARED_CR_ID"
