from __future__ import annotations

import json

from src.pipeline.extraction.calculator_source_gate import apply_source_gate


def test_source_gate_keeps_only_spec_covered_unblocked_disease(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    specs.joinpath("314.json").write_text(json.dumps({"guideline_id": "314"}), encoding="utf-8")
    db = {"recommendations": [
        {"id": "aom", "cr_id": "314", "source_verification_status": "CALCULATOR_BOUND_VERIFIED"},
        {"id": "pinned_only", "cr_id": "314"},
        {"id": "missing", "cr_id": "999"},
        {"id": "known_block", "cr_id": "313_3", "calculation_blocked": True,
         "calculation_block_reason": "current PDF pending"},
    ]}
    stats = apply_source_gate(db, specs)
    assert stats == {"covered_unblocked": 1, "already_blocked": 1, "newly_blocked": 2}
    assert db["recommendations"][0].get("calculation_blocked") is None
    assert db["recommendations"][1]["calculation_blocked"] is True
    assert db["recommendations"][1]["source_verification_status"] == "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
    assert db["recommendations"][2]["source_verification_status"] == "SOURCE_SPEC_MISSING"
    assert db["recommendations"][3]["calculation_block_reason"] == "current PDF pending"
