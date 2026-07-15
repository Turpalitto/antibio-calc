"""P3 curation-support tooling tests (non-clinical).

Covers build_conflict_worklist, validate_curation, build_golden_template.
Proves the tools NEVER make a clinical decision: triage is lexical only,
validation reuses the frozen decision rules, and golden templates ship with an
empty `expect` (so they cannot pass as real cases until a physician fills them).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clinical_engine.tools import (
    build_conflict_worklist,
    build_golden_template,
    validate_curation,
)


def _ledger(tmp_path: Path, decisions: list[dict]) -> Path:
    p = tmp_path / "decisions.json"
    p.write_text(json.dumps({"meta": {"status": "PENDING_PHYSICIAN_REVIEW"},
                             "decisions": decisions}, ensure_ascii=False), encoding="utf-8")
    return p


def _conflict(dx, opts, **extra):
    d = {"conflict_id": "c_" + dx, "diagnosis": dx, "severity": "CRITICAL",
         "conflict_type": "DIFFERENT_ICD", "guideline_options": opts,
         "decision": "pending_review"}
    d.update(extra)
    return d


# ── triage is lexical only, no clinical judgement ──────────────


def test_triage_flags_name_title_disjoint(tmp_path: Path):
    # Diagnosis name shares no word with any option title + different ICDs.
    rec = _conflict("Пневмоцистная пневмония",
                    [{"guideline_id": "1", "icd10": ["M08.2"], "title": "Юношеский артрит"},
                     {"guideline_id": "2", "icd10": ["M34.0"], "title": "Системный склероз"}])
    assert build_conflict_worklist.triage_hint(rec) == "NAME_TITLE_DISJOINT"


def test_triage_flags_likely_duplicate(tmp_path: Path):
    rec = _conflict("Цистит",
                    [{"guideline_id": "1", "icd10": ["N30.0"], "title": "Цистит"},
                     {"guideline_id": "2", "icd10": ["N30.0"], "title": "Цистит"}])
    assert build_conflict_worklist.triage_hint(rec) == "LIKELY_DUPLICATE"


def test_worklist_writes_md_and_csv_and_never_decides(tmp_path: Path):
    led = _ledger(tmp_path, [
        _conflict("Пневмоцистная пневмония",
                  [{"guideline_id": "1", "icd10": ["M08.2"], "title": "Юношеский артрит"},
                   {"guideline_id": "2", "icd10": ["M34.0"], "title": "Системный склероз"}]),
    ])
    r = build_conflict_worklist.build(str(led), str(tmp_path / "wl.md"), str(tmp_path / "wl.csv"))
    assert r["total"] == 1 and r["pending"] == 1
    md = (tmp_path / "wl.md").read_text(encoding="utf-8")
    # The worklist must state its hints are not clinical recommendations.
    assert "NOT clinical recommendations" in md
    # It must not fabricate a chosen guideline anywhere.
    assert "chosen_guideline_id" not in md


# ── validation reuses frozen rules, blocks on missing attribution ──


def test_validate_pending_blocks_production(tmp_path: Path):
    led = _ledger(tmp_path, [_conflict("DX", [{"guideline_id": "1", "icd10": ["A"], "title": "t"},
                                              {"guideline_id": "2", "icd10": ["B"], "title": "t2"}])])
    r = validate_curation.validate(str(led))
    assert r["pending"] == 1 and r["production_ready"] is False
    assert r["would_be_status"] == "PARTIALLY_CURATED"


def test_validate_flags_unattributed_decision(tmp_path: Path):
    # A decision without decided_by/rationale is INVALID (blocks production).
    rec = _conflict("DX", [{"guideline_id": "1", "icd10": ["A"], "title": "t"},
                           {"guideline_id": "2", "icd10": ["B"], "title": "t2"}],
                    decision="select_primary", chosen_guideline_id="1")
    led = _ledger(tmp_path, [rec])
    r = validate_curation.validate(str(led))
    assert r["invalid"] == 1 and r["production_ready"] is False


def test_validate_accepts_fully_attributed_decision(tmp_path: Path):
    rec = _conflict("DX", [{"guideline_id": "1", "icd10": ["A"], "title": "t"},
                           {"guideline_id": "2", "icd10": ["B"], "title": "t2"}],
                    decision="select_primary", chosen_guideline_id="1",
                    decided_by="Тестов Т.Т., ЛОР", decided_at="2026-07-11T00:00:00Z",
                    rationale="test rationale")
    led = _ledger(tmp_path, [rec])
    r = validate_curation.validate(str(led))
    assert r["invalid"] == 0 and r["pending"] == 0 and r["production_ready"] is True
    assert r["would_be_status"] == "PRODUCTION_CURATED"


# ── golden template ships clinically empty ─────────────────────


def test_golden_template_has_empty_expect(tmp_path: Path):
    r = build_golden_template.build("Эпиглоттит", "J05.1", "1832", str(tmp_path))
    assert r["expect_is_empty"] is True
    doc = json.loads(Path(r["out"]).read_text(encoding="utf-8"))
    assert doc["expect"] == {}
    # No physician_review dimension is pre-approved.
    assert all(v.get("approved") is False for v in doc["physician_review"].values())
    # File is '_'-prefixed so the runner won't execute it as a real case.
    assert Path(r["out"]).name.startswith("_")


def test_golden_template_not_loaded_as_case(tmp_path: Path):
    from clinical_engine.golden_cases import runner
    build_golden_template.build("Эпиглоттит", "J05.1", "1832", str(tmp_path))
    cases = runner.load_cases(tmp_path)  # skips '_'-prefixed files
    assert cases == []
