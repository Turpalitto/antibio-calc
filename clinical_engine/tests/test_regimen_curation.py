"""P3 INT-3 — physician-gated regimen review ledger + curated view tests.

Builds a throwaway mini-corpus and exercises: scaffolding (pending, no
auto-approval, merge-preserving), deterministic curated build, provenance
preservation, and every INT-3 validation failure mode
(DUPLICATE_DECISION, MISSING_REGIMEN, SHA_MISMATCH, UNRESOLVED_DECISION,
ORPHAN_REVIEW). Upstream is never written.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.tools import (
    build_curated_regimens,
    build_regimen_ledger,
    validate_regimen_curation,
)

_PDF = b"%PDF-1.4 test\n"
_SHA = hashlib.sha256(_PDF).hexdigest()


def _corpus(root: Path, regimens=(("5351", "343"), ("5352", "343"))) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "downloads_active").mkdir(exist_ok=True)
    (root / "downloads_active" / "g.pdf").write_bytes(_PDF)
    nr = sqlite3.connect(root / "normalized_regimens.sqlite")
    nr.execute("CREATE TABLE normalized_regimens (regimen_id TEXT, guideline_id TEXT, "
               "review_status TEXT, reviewed_by TEXT, review_date TEXT, approved INTEGER)")
    md = sqlite3.connect(root / "metadata.sqlite")
    md.execute("CREATE TABLE antibiotic_regimens (id INTEGER, clinrec_id INTEGER, pdf_file TEXT, "
               "pdf_sha256 TEXT, page_number TEXT, source_quote TEXT, section_name TEXT)")
    md.execute("CREATE TABLE clinrecs (id INTEGER, code INTEGER)")
    md.execute("INSERT INTO clinrecs VALUES (343, 494)")
    for rid, gid in regimens:
        nr.execute("INSERT INTO normalized_regimens VALUES (?,?, 'pending','',NULL,0)", (rid, gid))
        md.execute("INSERT INTO antibiotic_regimens VALUES (?,343,'g.pdf',?, '27','q','Лечение')",
                   (int(rid), _SHA))
    nr.commit(); nr.close(); md.commit(); md.close()


def _loc(root: Path) -> CorpusLocator:
    return CorpusLocator(root)


def _decide(rid, gid, decision, sha=_SHA, **over):
    d = {"regimen_id": rid, "guideline_id": gid, "pdf_sha256": sha, "decision": decision,
         "decided_by": "Тестов Т.Т., ЛОР", "decided_at": "2026-07-11T00:00:00Z",
         "rationale": "verified vs guideline",
         "review_status": {"approve": "APPROVED", "reject": "REJECTED"}.get(decision, "PENDING")}
    d.update(over)
    return d


def _write_ledger(path: Path, decisions: list[dict]) -> None:
    path.write_text(json.dumps({"meta": {}, "decisions": decisions}, ensure_ascii=False),
                    encoding="utf-8")


# ── scaffolding ────────────────────────────────────────────────


def test_scaffold_lists_pending_never_approves(tmp_path):
    _corpus(tmp_path / "corpus")
    led = tmp_path / "ledger.json"
    r = build_regimen_ledger.build(str(led), guideline_id="343", locator=_loc(tmp_path / "corpus"))
    assert r["added"] == 2 and r["pending"] == 2
    doc = json.loads(led.read_text(encoding="utf-8"))
    assert all(d["decision"] == "pending_review" for d in doc["decisions"])
    assert all(d["decided_by"] == "" for d in doc["decisions"])
    # required binding fields present
    for d in doc["decisions"]:
        assert d["pdf_sha256"] == _SHA and d["guideline_id"] == "343"


def test_scaffold_is_merge_preserving(tmp_path):
    _corpus(tmp_path / "corpus")
    led = tmp_path / "ledger.json"
    build_regimen_ledger.build(str(led), guideline_id="343", locator=_loc(tmp_path / "corpus"))
    # physician approves 5351
    doc = json.loads(led.read_text(encoding="utf-8"))
    for d in doc["decisions"]:
        if d["regimen_id"] == "5351":
            d.update(_decide("5351", "343", "approve"))
    led.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    # re-scaffold must NOT wipe the decision
    build_regimen_ledger.build(str(led), guideline_id="343", locator=_loc(tmp_path / "corpus"))
    doc2 = json.loads(led.read_text(encoding="utf-8"))
    d5351 = next(d for d in doc2["decisions"] if d["regimen_id"] == "5351")
    assert d5351["decision"] == "approve" and d5351["decided_by"]


# ── deterministic curated build + provenance ───────────────────


def test_curated_build_approves_with_provenance(tmp_path):
    _corpus(tmp_path / "corpus")
    led = tmp_path / "ledger.json"
    _write_ledger(led, [_decide("5351", "343", "approve"), _decide("5352", "343", "reject")])
    out, audit = tmp_path / "curated.json", tmp_path / "audit.json"
    r = build_curated_regimens.build(str(led), str(out), str(audit), locator=_loc(tmp_path / "corpus"))
    assert r["status"] == "PRODUCTION_CURATED"
    assert r["approved"] == 1 and r["rejected"] == 1
    doc = json.loads(out.read_text(encoding="utf-8"))
    e = doc["approved_regimens"][0]
    # full provenance preserved back to upstream
    for k in ("regimen_id", "guideline_id", "kr_code", "pdf_sha256", "pdf_path",
              "page_number", "decided_by", "rationale", "review_status"):
        assert e[k] not in (None, "")
    assert e["pdf_sha256_verified"] is True
    # no clinical content duplicated (no drug/dose/source_quote fields)
    assert "source_quote" not in e and "drug" not in e and "dose" not in e


def test_curated_build_is_deterministic(tmp_path):
    _corpus(tmp_path / "corpus")
    led = tmp_path / "ledger.json"
    _write_ledger(led, [_decide("5352", "343", "approve"), _decide("5351", "343", "approve")])
    out1, out2 = tmp_path / "c1.json", tmp_path / "c2.json"
    build_curated_regimens.build(str(led), str(out1), str(tmp_path/"a1.json"), locator=_loc(tmp_path/"corpus"))
    build_curated_regimens.build(str(led), str(out2), str(tmp_path/"a2.json"), locator=_loc(tmp_path/"corpus"))
    d1 = json.loads(out1.read_text(encoding="utf-8"))["approved_regimens"]
    d2 = json.loads(out2.read_text(encoding="utf-8"))["approved_regimens"]
    assert d1 == d2
    assert [e["regimen_id"] for e in d1] == ["5351", "5352"]  # sorted, deterministic


# ── validation failure modes (INT-3 req 5) ─────────────────────


def _build(tmp_path, decisions):
    _corpus(tmp_path / "corpus")
    led = tmp_path / "ledger.json"
    _write_ledger(led, decisions)
    return build_curated_regimens.build(str(led), str(tmp_path/"c.json"),
                                        str(tmp_path/"a.json"), locator=_loc(tmp_path/"corpus"))


def test_fail_duplicate_decision(tmp_path):
    r = _build(tmp_path, [_decide("5351", "343", "approve"), _decide("5351", "343", "reject")])
    assert r["errors_by_type"].get("DUPLICATE_DECISION") == 1
    assert r["status"] == "PARTIALLY_CURATED"


def test_fail_missing_regimen(tmp_path):
    r = _build(tmp_path, [_decide("9999", "343", "approve")])
    assert r["errors_by_type"].get("MISSING_REGIMEN") == 1


def test_fail_sha_mismatch(tmp_path):
    r = _build(tmp_path, [_decide("5351", "343", "approve", sha="0"*64)])
    assert r["errors_by_type"].get("SHA_MISMATCH") == 1


def test_fail_unresolved_pending(tmp_path):
    r = _build(tmp_path, [_decide("5351", "343", "pending_review")])
    assert r["unresolved"] == 1 and r["status"] == "PARTIALLY_CURATED"


def test_fail_unresolved_missing_attribution(tmp_path):
    r = _build(tmp_path, [_decide("5351", "343", "approve", decided_by="")])
    assert r["unresolved"] == 1


def test_fail_orphan_review_wrong_guideline(tmp_path):
    # regimen 5351's real guideline is 343; ledger claims 999 -> orphan.
    r = _build(tmp_path, [_decide("5351", "999", "approve")])
    assert r["errors_by_type"].get("ORPHAN_REVIEW") == 1


# ── read-only validator / CI gate ──────────────────────────────


def test_validator_reports_progress(tmp_path):
    _corpus(tmp_path / "corpus")
    led = tmp_path / "ledger.json"
    _write_ledger(led, [_decide("5351", "343", "approve"), _decide("5352", "343", "pending_review")])
    r = validate_regimen_curation.validate(str(led), locator=_loc(tmp_path / "corpus"))
    assert r["approved"] == 1 and r["unresolved"] == 1
    assert r["production_ready"] is False


def test_upstream_untouched_after_build(tmp_path):
    _corpus(tmp_path / "corpus")
    corpus = tmp_path / "corpus"
    before = {p.name: p.stat().st_mtime for p in corpus.rglob("*") if p.is_file()}
    led = tmp_path / "ledger.json"
    _write_ledger(led, [_decide("5351", "343", "approve")])
    build_curated_regimens.build(str(led), str(tmp_path/"c.json"), str(tmp_path/"a.json"),
                                 locator=_loc(corpus))
    after = {p.name: p.stat().st_mtime for p in corpus.rglob("*") if p.is_file()}
    assert before == after  # no corpus file created or modified


# ── real corpus smoke (present) or skip ────────────────────────


def test_real_corpus_scaffold_and_build_smoke(tmp_path):
    loc = CorpusLocator()
    if not loc.available():
        pytest.skip("external corpus not present")
    led = tmp_path / "ledger.json"
    r = build_regimen_ledger.build(str(led), guideline_id="343", locator=loc)
    assert r["added"] == 11 and r["pending"] == 11   # typhoid guideline, all pending
    # build with no decisions -> PARTIALLY, nothing approved, upstream untouched
    out = build_curated_regimens.build(str(led), str(tmp_path/"c.json"), str(tmp_path/"a.json"),
                                       verify_pdf=False, locator=loc)
    assert out["status"] == "PARTIALLY_CURATED"
    assert out["approved"] == 0 and out["unresolved"] == 11
