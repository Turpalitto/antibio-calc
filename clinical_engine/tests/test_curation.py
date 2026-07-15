"""Milestone 11: physician-validation workflow (decision ledger + curated build).

Tests the tooling logic only (clinical_engine/tools/), not the engine. Proves:
never auto-selects, applies only attributed decisions, refuses PRODUCTION_CURATED
while unresolved, and is reversible.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clinical_engine.readers.diagnosis_reader import JsonDiagnosisProvider
from clinical_engine.tools import build_curated_index, build_decision_ledger


def _entry(gid: str, dx: str, icd: list[str], title: str) -> dict:
    return {
        "guideline_id": gid, "diagnosis_name": dx, "icd10_codes": icd,
        "guideline_title": title, "guideline_year": None,
        "guideline_revision_date": None, "source_url": "",
    }


@pytest.fixture
def workspace(tmp_path: Path):
    # Two conflicts (DX_A critical, DX_B duplicate) + one non-conflict (DX_C).
    entries = [
        _entry("g1", "DX_A", ["X1"], "Guideline One"),
        _entry("g2", "DX_A", ["X2"], "Guideline Two"),
        _entry("g3", "DX_B", ["Y"], "Dup Guideline"),
        _entry("g4", "DX_B", ["Y"], "Dup Guideline"),
        _entry("g5", "DX_C", ["Z"], "Solo Guideline"),
    ]
    draft = tmp_path / "diagnosis_index.json"
    draft.write_text(json.dumps({"meta": {"status": "AUTO_GENERATED_DRAFT"}, "entries": entries},
                                ensure_ascii=False), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"conflicts": [
        {"diagnosis": "DX_A", "severity": "CRITICAL", "conflict_type": "DIFFERENT_ICD",
         "guidelines": [{"guideline_id": "g1", "icd10": ["X1"], "titles": ["Guideline One"]},
                        {"guideline_id": "g2", "icd10": ["X2"], "titles": ["Guideline Two"]}]},
        {"diagnosis": "DX_B", "severity": "SAFE", "conflict_type": "LIKELY_DUPLICATE",
         "guidelines": [{"guideline_id": "g3", "icd10": ["Y"], "titles": ["Dup Guideline"]},
                        {"guideline_id": "g4", "icd10": ["Y"], "titles": ["Dup Guideline"]}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    ledger = tmp_path / "decisions.json"
    out = tmp_path / "curated.json"
    audit = tmp_path / "audit.json"
    return {"tmp": tmp_path, "draft": draft, "review": review,
            "ledger": ledger, "out": out, "audit": audit}


def _gen_ledger(ws):
    build_decision_ledger.build(str(ws["review"]), str(ws["ledger"]))


def _set_decision(ws, diagnosis: str, **fields) -> None:
    doc = json.loads(ws["ledger"].read_text(encoding="utf-8"))
    for rec in doc["decisions"]:
        if rec["diagnosis"] == diagnosis:
            rec.update(fields)
    ws["ledger"].write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _curate(ws):
    return build_curated_index.build(str(ws["draft"]), str(ws["ledger"]),
                                     str(ws["out"]), str(ws["audit"]))


def _curated_entries(ws):
    return json.loads(ws["out"].read_text(encoding="utf-8"))["entries"]


class TestLedgerGeneration:
    def test_all_conflicts_start_pending(self, workspace) -> None:
        _gen_ledger(workspace)
        doc = json.loads(workspace["ledger"].read_text(encoding="utf-8"))
        assert doc["meta"]["status"] == "PENDING_PHYSICIAN_REVIEW"
        assert doc["meta"]["pending"] == 2
        assert all(r["decision"] == "pending_review" for r in doc["decisions"])
        assert all(r["chosen_guideline_id"] is None for r in doc["decisions"])

    def test_regeneration_preserves_physician_decisions(self, workspace) -> None:
        _gen_ledger(workspace)
        _set_decision(workspace, "DX_A", decision="select_primary", chosen_guideline_id="g1",
                      decided_by="dr.house", decided_at="2026-07-10T00:00:00Z", rationale="test")
        # Regenerate — must NOT wipe the physician's DX_A decision.
        _gen_ledger(workspace)
        doc = json.loads(workspace["ledger"].read_text(encoding="utf-8"))
        dxa = next(r for r in doc["decisions"] if r["diagnosis"] == "DX_A")
        assert dxa["decision"] == "select_primary"
        assert dxa["chosen_guideline_id"] == "g1"
        assert dxa["decided_by"] == "dr.house"


class TestRefusesProductionWhenUnresolved:
    def test_all_pending_is_partial_not_production(self, workspace) -> None:
        _gen_ledger(workspace)
        r = _curate(workspace)
        assert r["status"] == "PARTIALLY_CURATED"
        assert r["pending"] == 2
        # Nothing dropped — unresolved conflicts pass through unchanged.
        assert r["entries_out"] == 5

    def test_one_pending_blocks_production(self, workspace) -> None:
        _gen_ledger(workspace)
        _set_decision(workspace, "DX_A", decision="keep_all_complementary",
                      decided_by="dr", decided_at="t", rationale="ok")
        # DX_B still pending -> cannot be production.
        r = _curate(workspace)
        assert r["status"] == "PARTIALLY_CURATED"


class TestDecisionApplication:
    def _resolve_both(self, ws, dx_a_fields):
        _gen_ledger(ws)
        _set_decision(ws, "DX_A", decided_by="dr", decided_at="t", rationale="r", **dx_a_fields)
        _set_decision(ws, "DX_B", decision="duplicate_keep_one", chosen_guideline_id="g3",
                      decided_by="dr", decided_at="t", rationale="dup")

    def test_select_primary_drops_others(self, workspace) -> None:
        self._resolve_both(workspace, {"decision": "select_primary", "chosen_guideline_id": "g1"})
        r = _curate(workspace)
        assert r["status"] == "PRODUCTION_CURATED"
        gids = {e["guideline_id"] for e in _curated_entries(workspace) if e["diagnosis_name"] == "DX_A"}
        assert gids == {"g1"}  # g2 dropped

    def test_duplicate_keep_one(self, workspace) -> None:
        self._resolve_both(workspace, {"decision": "select_primary", "chosen_guideline_id": "g2"})
        _curate(workspace)
        gids = {e["guideline_id"] for e in _curated_entries(workspace) if e["diagnosis_name"] == "DX_B"}
        assert gids == {"g3"}  # only kept guideline for DX_B

    def test_keep_all_complementary(self, workspace) -> None:
        self._resolve_both(workspace, {"decision": "keep_all_complementary"})
        _curate(workspace)
        gids = {e["guideline_id"] for e in _curated_entries(workspace) if e["diagnosis_name"] == "DX_A"}
        assert gids == {"g1", "g2"}

    def test_split_renames_per_guideline(self, workspace) -> None:
        self._resolve_both(workspace, {"decision": "split",
                                       "renames": {"g1": "DX_A (cond1)", "g2": "DX_A (cond2)"}})
        _curate(workspace)
        names = {e["diagnosis_name"] for e in _curated_entries(workspace) if e["guideline_id"] in ("g1", "g2")}
        assert names == {"DX_A (cond1)", "DX_A (cond2)"}

    def test_remove_diagnosis_drops_all(self, workspace) -> None:
        self._resolve_both(workspace, {"decision": "remove_diagnosis"})
        _curate(workspace)
        assert not [e for e in _curated_entries(workspace) if e["diagnosis_name"] == "DX_A"]

    def test_non_conflict_entry_always_passes_through(self, workspace) -> None:
        self._resolve_both(workspace, {"decision": "keep_all_complementary"})
        _curate(workspace)
        assert any(e["guideline_id"] == "g5" for e in _curated_entries(workspace))


class TestInvalidDecisions:
    def test_missing_attribution_is_invalid_not_applied(self, workspace) -> None:
        _gen_ledger(workspace)
        # decision set but NO decided_by/rationale -> invalid, must not apply.
        _set_decision(workspace, "DX_A", decision="select_primary", chosen_guideline_id="g1")
        _set_decision(workspace, "DX_B", decision="duplicate_keep_one", chosen_guideline_id="g3",
                      decided_by="dr", decided_at="t", rationale="dup")
        r = _curate(workspace)
        assert r["status"] == "PARTIALLY_CURATED"
        assert r["invalid"] == 1
        # DX_A unresolved -> both g1 and g2 still present.
        gids = {e["guideline_id"] for e in _curated_entries(workspace) if e["diagnosis_name"] == "DX_A"}
        assert gids == {"g1", "g2"}

    def test_chosen_guideline_not_in_options_is_invalid(self, workspace) -> None:
        _gen_ledger(workspace)
        _set_decision(workspace, "DX_A", decision="select_primary", chosen_guideline_id="NOPE",
                      decided_by="dr", decided_at="t", rationale="x")
        _set_decision(workspace, "DX_B", decision="keep_all_complementary",
                      decided_by="dr", decided_at="t", rationale="x")
        r = _curate(workspace)
        assert r["invalid"] == 1
        assert r["status"] == "PARTIALLY_CURATED"

    def test_split_must_cover_all_guidelines(self, workspace) -> None:
        _gen_ledger(workspace)
        _set_decision(workspace, "DX_A", decision="split", renames={"g1": "only one"},
                      decided_by="dr", decided_at="t", rationale="x")
        _set_decision(workspace, "DX_B", decision="keep_all_complementary",
                      decided_by="dr", decided_at="t", rationale="x")
        r = _curate(workspace)
        assert r["invalid"] == 1


class TestReversibility:
    def test_reverting_to_pending_restores_original(self, workspace) -> None:
        _gen_ledger(workspace)
        _set_decision(workspace, "DX_A", decision="remove_diagnosis",
                      decided_by="dr", decided_at="t", rationale="x")
        _set_decision(workspace, "DX_B", decision="keep_all_complementary",
                      decided_by="dr", decided_at="t", rationale="x")
        _curate(workspace)
        assert not [e for e in _curated_entries(workspace) if e["diagnosis_name"] == "DX_A"]
        # Reverse the DX_A decision -> rebuild -> DX_A restored unchanged.
        _set_decision(workspace, "DX_A", decision="pending_review", chosen_guideline_id=None,
                      renames=None, decided_by=None, decided_at=None, rationale=None)
        _curate(workspace)
        gids = {e["guideline_id"] for e in _curated_entries(workspace) if e["diagnosis_name"] == "DX_A"}
        assert gids == {"g1", "g2"}

    def test_draft_and_ledger_never_modified_by_build(self, workspace) -> None:
        _gen_ledger(workspace)
        draft_before = workspace["draft"].read_text(encoding="utf-8")
        ledger_before = workspace["ledger"].read_text(encoding="utf-8")
        _curate(workspace)
        assert workspace["draft"].read_text(encoding="utf-8") == draft_before
        assert workspace["ledger"].read_text(encoding="utf-8") == ledger_before


class TestAuditTrail:
    def test_audit_records_applied_decision(self, workspace) -> None:
        _gen_ledger(workspace)
        _set_decision(workspace, "DX_A", decision="select_primary", chosen_guideline_id="g1",
                      decided_by="dr.house", decided_at="2026-07-10T00:00:00Z", rationale="clinical reason")
        _set_decision(workspace, "DX_B", decision="keep_all_complementary",
                      decided_by="dr.house", decided_at="2026-07-10T00:00:00Z", rationale="both valid")
        _curate(workspace)
        audit = json.loads(workspace["audit"].read_text(encoding="utf-8"))
        assert audit["status"] == "PRODUCTION_CURATED"
        applied = {a["diagnosis"]: a for a in audit["applied_decisions"]}
        assert applied["DX_A"]["decided_by"] == "dr.house"
        assert applied["DX_A"]["rationale"] == "clinical reason"
        assert applied["DX_A"]["dropped_guideline_ids"] == ["g2"]


class TestCuratedIndexLoadable:
    def test_curated_index_loads_via_provider(self, workspace) -> None:
        _gen_ledger(workspace)
        _set_decision(workspace, "DX_A", decision="select_primary", chosen_guideline_id="g1",
                      decided_by="dr", decided_at="t", rationale="x")
        _set_decision(workspace, "DX_B", decision="keep_all_complementary",
                      decided_by="dr", decided_at="t", rationale="x")
        _curate(workspace)
        provider = JsonDiagnosisProvider(workspace["out"])
        assert provider.meta["status"] == "PRODUCTION_CURATED"
        assert provider.lookup("DX_A", None)[0].guideline_id == "g1"
