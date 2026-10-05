from __future__ import annotations

import json

from src.pipeline.extraction.calculator_source_gate import apply_source_gate


def test_source_gate_blocks_only_explicitly_marked_records(tmp_path):
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
    # explicit-marks policy: only the source-marked record stays blocked;
    # unmarked records (no flag, no status) remain computable.
    assert stats == {"covered_unblocked": 3, "already_blocked": 1, "newly_blocked": 0}
    assert db["recommendations"][0].get("calculation_blocked") is None
    assert db["recommendations"][1]["calculation_blocked"] is False
    assert db["recommendations"][1]["source_verification_status"] == "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
    assert db["recommendations"][2]["calculation_blocked"] is False
    assert db["recommendations"][2]["source_verification_status"] == "CR_REFERENCE_CALCULATION"
    assert db["recommendations"][3]["calculation_blocked"] is True
    assert db["recommendations"][3]["calculation_block_reason"] == "current PDF pending"


def test_source_gate_blocks_pending_status_even_without_block_flag(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    db = {"recommendations": [
        {"id": "pdf_pending", "cr_id": "313_3",
         "source_verification_status": "CURRENT_WEB_CONFIRMED_PDF_PENDING"},
    ]}
    stats = apply_source_gate(db, specs)
    assert stats == {"covered_unblocked": 0, "already_blocked": 0, "newly_blocked": 1}
    rec = db["recommendations"][0]
    assert rec["calculation_blocked"] is True
    assert rec["source_verification_status"] == "CURRENT_WEB_CONFIRMED_PDF_PENDING"
    assert rec["calculation_block_reason"]


def test_source_gate_never_clears_an_explicit_block(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    specs.joinpath("314.json").write_text(json.dumps({"guideline_id": "314"}), encoding="utf-8")
    db = {"recommendations": [
        {"id": "marked_verified", "cr_id": "314",
         "source_verification_status": "CALCULATOR_BOUND_VERIFIED",
         "calculation_blocked": True, "calculation_block_reason": "owner hold"},
    ]}
    stats = apply_source_gate(db, specs)
    assert stats == {"covered_unblocked": 0, "already_blocked": 1, "newly_blocked": 0}
    rec = db["recommendations"][0]
    assert rec["calculation_blocked"] is True
    assert rec["calculation_block_reason"] == "owner hold"


def test_unblock_all_escape_hatch_unblocks_everything(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    db = {"recommendations": [
        {"id": "marked", "cr_id": "313_3", "calculation_blocked": True,
         "calculation_block_reason": "current PDF pending"},
        {"id": "plain", "cr_id": "999"},
    ]}
    stats = apply_source_gate(db, specs, unblock_all=True)
    assert stats == {"covered_unblocked": 2, "already_blocked": 0, "newly_blocked": 0}
    for rec in db["recommendations"]:
        assert rec["calculation_blocked"] is False
        assert "calculation_block_reason" not in rec
