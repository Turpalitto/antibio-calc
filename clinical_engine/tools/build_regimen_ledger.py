"""Scaffold / update the physician regimen-review ledger (P3 INT-3).

Reads the external corpus READ-ONLY and produces a repo-side ledger of regimens
awaiting physician review. Each entry binds a regimen to the exact source PDF it
was extracted from via ``pdf_sha256`` — so if the upstream PDF ever changes, the
binding breaks and the regimen must be re-reviewed (see build_curated_regimens).

The physician edits ``regimen_review_ledger.json`` (it lives in the repo, never
in the corpus). This tool NEVER makes a clinical decision; it only lists regimens
as ``pending_review``. It is MERGE-PRESERVING: existing physician decisions are
kept untouched; only regimens not yet in the ledger are added as pending.

Upstream is never modified. Only regimen_id / guideline_id / pdf_sha256 (keys and
an integrity hash — NOT clinical content) are written to the repo.

Usage (from repo root):
    # add every regimen of one guideline as pending (incremental review)
    python -m clinical_engine.tools.build_regimen_ledger --guideline-id 343
    # or a specific set
    python -m clinical_engine.tools.build_regimen_ledger --regimen-ids 5351 5352
    # or the whole corpus
    python -m clinical_engine.tools.build_regimen_ledger --all
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clinical_engine.corpus.locator import CorpusLocator

_DEFAULT_LEDGER = "regimen_review_ledger.json"

DECISION_VOCABULARY = {
    "pending_review": "not decided yet (default — awaits physician)",
    "approve": "regimen is clinically correct per the guideline (keep in curated view)",
    "reject": "extraction error / clinically wrong (exclude from curated view)",
    "needs_revision": "requires correction upstream before it can be approved (unresolved)",
}


def _empty_ledger() -> dict:
    return {
        "meta": {
            "status": "PENDING_PHYSICIAN_REVIEW",
            "policy": (
                "NEVER approve automatically. Each regimen is reviewed by a physician against "
                "the original Russian Clinical Guideline. A non-pending decision MUST carry "
                "decided_by, decided_at, rationale, review_status, and a pdf_sha256 that matches "
                "the upstream source. Decisions are reversible (edit and rebuild). Upstream is "
                "read-only; generated artifacts are never hand-edited."
            ),
            "decision_vocabulary": DECISION_VOCABULARY,
            "review_status_vocabulary": ["PENDING", "APPROVED", "REJECTED", "NEEDS_REVISION"],
        },
        "decisions": [],
    }


def _load_ledger(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return _empty_ledger()


def _pdf_sha_for(md_conn, regimen_id: str) -> str | None:
    row = md_conn.execute(
        "SELECT pdf_sha256 FROM antibiotic_regimens WHERE id = ?", (regimen_id,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _select_regimen_ids(nr_conn, *, guideline_id: str | None,
                        regimen_ids: list[str] | None, all_: bool) -> list[tuple[str, str]]:
    if regimen_ids:
        out = []
        for rid in regimen_ids:
            r = nr_conn.execute(
                "SELECT regimen_id, guideline_id FROM normalized_regimens WHERE regimen_id = ?",
                (rid,),
            ).fetchone()
            if r:
                out.append((str(r[0]), str(r[1])))
        return out
    if guideline_id:
        return [(str(a), str(b)) for a, b in nr_conn.execute(
            "SELECT regimen_id, guideline_id FROM normalized_regimens WHERE guideline_id = ? "
            "ORDER BY regimen_id", (guideline_id,))]
    if all_:
        return [(str(a), str(b)) for a, b in nr_conn.execute(
            "SELECT regimen_id, guideline_id FROM normalized_regimens ORDER BY regimen_id")]
    return []


def build(ledger_path: str, *, guideline_id: str | None = None,
          regimen_ids: list[str] | None = None, all_: bool = False,
          locator: CorpusLocator | None = None) -> dict:
    loc = locator or CorpusLocator()
    loc.require()  # fail loudly if corpus absent
    ledger = _load_ledger(Path(ledger_path))
    existing = {d["regimen_id"] for d in ledger["decisions"]}

    nr = loc.open_normalized_regimens()
    md = loc.open_metadata()
    try:
        wanted = _select_regimen_ids(nr, guideline_id=guideline_id,
                                     regimen_ids=regimen_ids, all_=all_)
        added = 0
        for rid, gid in wanted:
            if rid in existing:
                continue  # never overwrite an existing (possibly decided) entry
            ledger["decisions"].append({
                "regimen_id": rid,
                "guideline_id": gid,
                "pdf_sha256": _pdf_sha_for(md, rid),
                "decision": "pending_review",
                "decided_by": "",
                "decided_at": "",
                "rationale": "",
                "review_status": "PENDING",
            })
            existing.add(rid)
            added += 1
    finally:
        nr.close(); md.close()

    ledger["decisions"].sort(key=lambda d: d["regimen_id"])
    pending = sum(1 for d in ledger["decisions"] if d.get("decision", "pending_review") == "pending_review")
    ledger["meta"]["total"] = len(ledger["decisions"])
    ledger["meta"]["pending"] = pending
    Path(ledger_path).write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ledger": ledger_path, "total": len(ledger["decisions"]), "added": added, "pending": pending}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    ap.add_argument("--guideline-id", default=None)
    ap.add_argument("--regimen-ids", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    r = build(args.ledger, guideline_id=args.guideline_id,
              regimen_ids=args.regimen_ids, all_=args.all)
    print("=== regimen review ledger ===")
    print(f"total {r['total']}  added {r['added']}  pending {r['pending']}")
    print(f"written: {r['ledger']}")
    print("NOTE: pending entries await physician decision (decided_by/rationale). No auto-approval.")


if __name__ == "__main__":
    main()
