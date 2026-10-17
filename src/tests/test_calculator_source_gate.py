from __future__ import annotations

import json

import pytest

from src.pipeline.extraction.calculator_source_gate import (
    NO_BASIS_REASON,
    NO_CR_POLICY_REASON,
    apply_source_gate,
    is_federal_cr_id,
)


def _specs(tmp_path, *guideline_ids):
    specs = tmp_path / "specs"
    specs.mkdir()
    for gid in guideline_ids:
        specs.joinpath(f"{gid}.json").write_text(json.dumps({"guideline_id": gid}), encoding="utf-8")
    return specs


def test_source_gate_blocks_only_explicitly_marked_records(tmp_path):
    specs = _specs(tmp_path, "314")
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
    assert stats == {"covered_unblocked": 3, "already_blocked": 1, "newly_blocked": 0,
                     "no_cr_expert_basis": 0, "basis_missing_blocked": 0}
    # B-7: every record leaves the gate with an explicit boolean, including the verified one.
    assert db["recommendations"][0]["calculation_blocked"] is False
    assert db["recommendations"][0]["source_verification_status"] == "CALCULATOR_BOUND_VERIFIED"
    assert db["recommendations"][1]["calculation_blocked"] is False
    assert db["recommendations"][1]["source_verification_status"] == "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
    assert db["recommendations"][2]["calculation_blocked"] is False
    assert db["recommendations"][2]["source_verification_status"] == "CR_REFERENCE_CALCULATION"
    assert db["recommendations"][3]["calculation_blocked"] is True
    assert db["recommendations"][3]["calculation_block_reason"] == "current PDF pending"
    assert all(isinstance(r["calculation_blocked"], bool) for r in db["recommendations"])


def test_source_gate_blocks_pending_status_even_without_block_flag(tmp_path):
    specs = _specs(tmp_path)
    db = {"recommendations": [
        {"id": "pdf_pending", "cr_id": "313_3",
         "source_verification_status": "CURRENT_WEB_CONFIRMED_PDF_PENDING"},
    ]}
    stats = apply_source_gate(db, specs)
    assert stats["newly_blocked"] == 1 and stats["covered_unblocked"] == 0
    rec = db["recommendations"][0]
    assert rec["calculation_blocked"] is True
    assert rec["source_verification_status"] == "CURRENT_WEB_CONFIRMED_PDF_PENDING"
    assert rec["calculation_block_reason"]


def test_source_gate_never_clears_an_explicit_block(tmp_path):
    specs = _specs(tmp_path, "314")
    db = {"recommendations": [
        {"id": "marked_verified", "cr_id": "314",
         "source_verification_status": "CALCULATOR_BOUND_VERIFIED",
         "calculation_blocked": True, "calculation_block_reason": "owner hold"},
        {"id": "extracted", "cr_id": "66_4", "calculation_blocked": True,
         "source_verification_status": "EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW",
         "calculation_block_reason": "pending physician review"},
    ]}
    stats = apply_source_gate(db, specs)
    assert stats["already_blocked"] == 2 and stats["newly_blocked"] == 0
    for rec, reason in zip(db["recommendations"], ("owner hold", "pending physician review")):
        assert rec["calculation_blocked"] is True
        assert rec["calculation_block_reason"] == reason
    assert db["recommendations"][1]["source_verification_status"] == "EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW"


def test_unblock_all_escape_hatch_unblocks_everything(tmp_path):
    specs = _specs(tmp_path)
    db = {"recommendations": [
        {"id": "marked", "cr_id": "313_3", "calculation_blocked": True,
         "calculation_block_reason": "current PDF pending"},
        {"id": "plain", "cr_id": "999"},
        {"id": "no_cr", "cr_id": "—", "cr_note": "СКАТ 2018"},
        {"id": "no_basis", "cr_id": "—"},
    ]}
    stats = apply_source_gate(db, specs, unblock_all=True)
    assert stats["covered_unblocked"] == 4 and stats["newly_blocked"] == 0
    for rec in db["recommendations"]:
        assert rec["calculation_blocked"] is False
        assert "calculation_block_reason" not in rec
    # the escape hatch unblocks, but it never mislabels a non-CR record as CR-referenced
    assert db["recommendations"][2]["source_verification_status"] == "NO_FEDERAL_CR_EXPERT_BASIS"
    assert db["recommendations"][3]["source_verification_status"] == "SOURCE_BASIS_MISSING"


# ---- B-2: records without a federal CR id ---------------------------------------


@pytest.mark.parametrize("value,expected", [
    ("314", True), ("313_3", True), ("66_4", True), ("980_1", True),
    ("—", False), ("", False), (None, False), ("IDSA-2019", False), ("314a", False), ("3_14_1", False),
])
def test_is_federal_cr_id(value, expected):
    assert is_federal_cr_id(value) is expected


def test_no_cr_record_with_documented_basis_is_labelled_not_cr_referenced(tmp_path):
    specs = _specs(tmp_path)
    db = {"recommendations": [
        {"id": "pid", "cr_id": "—", "cr_note": "Схема по СКАТ (2018) и IDSA; федеральной КР нет."},
    ]}
    stats = apply_source_gate(db, specs)
    rec = db["recommendations"][0]
    assert rec["calculation_blocked"] is False
    assert rec["source_verification_status"] == "NO_FEDERAL_CR_EXPERT_BASIS"
    assert "calculation_block_reason" not in rec
    assert stats["no_cr_expert_basis"] == 1 and stats["covered_unblocked"] == 1


def test_no_cr_record_without_any_basis_is_blocked(tmp_path):
    specs = _specs(tmp_path)
    db = {"recommendations": [
        {"id": "erysipelas", "cr_id": "—"},
        {"id": "blank_note", "cr_id": "—", "cr_note": "   "},
        {"id": "no_cr_key"},
    ]}
    stats = apply_source_gate(db, specs)
    for rec in db["recommendations"]:
        assert rec["calculation_blocked"] is True
        assert rec["source_verification_status"] == "SOURCE_BASIS_MISSING"
        assert rec["calculation_block_reason"] == NO_BASIS_REASON
    assert stats["basis_missing_blocked"] == 3 and stats["newly_blocked"] == 3


def test_block_no_cr_policy_blocks_documented_non_cr_records_too(tmp_path):
    specs = _specs(tmp_path)
    db = {"recommendations": [
        {"id": "pid", "cr_id": "—", "cr_note": "СКАТ 2018"},
        {"id": "cap", "cr_id": "654"},
    ]}
    stats = apply_source_gate(db, specs, block_no_cr=True)
    pid, cap = db["recommendations"]
    assert pid["calculation_blocked"] is True
    assert pid["calculation_block_reason"] == NO_CR_POLICY_REASON
    assert pid["source_verification_status"] == "NO_FEDERAL_CR_EXPERT_BASIS"
    assert cap["calculation_blocked"] is False
    assert cap["source_verification_status"] == "CR_REFERENCE_CALCULATION"
    assert stats == {"covered_unblocked": 1, "already_blocked": 0, "newly_blocked": 1,
                     "no_cr_expert_basis": 1, "basis_missing_blocked": 0}


def test_gate_is_idempotent(tmp_path):
    specs = _specs(tmp_path, "314")
    db = {"recommendations": [
        {"id": "aom", "cr_id": "314", "source_verification_status": "CALCULATOR_BOUND_VERIFIED"},
        {"id": "cap", "cr_id": "654"},
        {"id": "pid", "cr_id": "—", "cr_note": "СКАТ"},
        {"id": "none", "cr_id": "—"},
        {"id": "held", "cr_id": "313_3", "calculation_blocked": True, "calculation_block_reason": "hold"},
    ]}
    apply_source_gate(db, specs)
    first = json.dumps(db, sort_keys=True, ensure_ascii=False)
    stats = apply_source_gate(db, specs)
    assert json.dumps(db, sort_keys=True, ensure_ascii=False) == first
    # second pass sees the basis-missing record as an explicit mark (already blocked)
    assert stats["already_blocked"] == 2 and stats["newly_blocked"] == 0
