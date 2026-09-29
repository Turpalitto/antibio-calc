#!/usr/bin/env python
"""
ANTIBIO Architectural Invariant checker (Design by Contract).

Enforces the machine-checkable invariants in ARCHITECTURAL_INVARIANTS.md against a Knowledge Base
SQLite file. Each invariant returns PASS/FAIL with a violation count and sample offending ids.
Exit code is non-zero if any BLOCKING invariant fails — so this gates CI and milestone closure.

Usage:
    python -m src.pipeline.knowledge_invariants --db kb_p44.db
    python -m src.pipeline.knowledge_invariants --db kb_p44.db --json inv_report.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

ALLOWED_STATUSES = {
    "draft", "extracted", "validated", "reviewed", "published",
    "superseded", "deprecated", "archived", "active",
}

# H-10: Frequency/Duration/Route used to be stored under type='Dose' with
# unit=NULL, so a "Every Dose has a unit" check either had to be advisory (and so
# could never block CI) or it fired on rows that were never doses.  They now have
# their own types, which makes the check meaningful AND enforceable for real doses.
# Only a genuine Dose is subject to it.
NON_DOSE_TYPES = ("Frequency", "Duration", "Route")


@dataclass
class Result:
    id: str
    name: str
    blocking: bool
    passed: bool
    violations: int
    sample: List[str] = field(default_factory=list)
    note: str = ""


def _q(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def check(conn: sqlite3.Connection) -> List[Result]:
    results: List[Result] = []

    def add(id_, name, blocking, sql_violations: str, note="", advisory_ok=False):
        rows = _q(conn, sql_violations)
        n = len(rows)
        results.append(Result(id_, name, blocking and not advisory_ok, n == 0, n,
                              [str(r[0]) for r in rows[:5]], note))

    # INV-01 — every object has >=1 provenance
    add("INV-01", "Every Knowledge Object has provenance", True,
        "SELECT o.id FROM objects o LEFT JOIN provenance p ON p.obj_id=o.id "
        "WHERE p.obj_id IS NULL")

    # INV-02 — provenance references an existing object
    add("INV-02", "Provenance references existing object", True,
        "SELECT p.obj_id FROM provenance p LEFT JOIN objects o ON o.id=p.obj_id "
        "WHERE o.id IS NULL")

    # INV-03 — table-origin provenance retains row/col
    add("INV-03", "Table-derived provenance retains table_row/col", True,
        "SELECT obj_id FROM provenance "
        "WHERE (semantic_engine LIKE '%table%' OR (layout_engine IS NOT NULL AND layout_engine != 'none')) "
        "AND table_row IS NULL")

    # INV-05 — a genuine Dose has a unit.  NON-ADVISORY: with Frequency/Duration/
    # Route no longer stored as unit-less Doses (H-10), any violation here is a real
    # dose missing its unit, and that must be able to block CI.
    non_dose_sql = ",".join("'%s'" % t for t in NON_DOSE_TYPES)
    add("INV-05", "Every Dose has a unit", True,
        f"SELECT id FROM objects WHERE type='Dose' AND type NOT IN ({non_dose_sql}) "
        f"AND (content NOT LIKE '%\"unit\"%' OR content LIKE '%\"unit\": null%' "
        f"OR content LIKE '%\"unit\": \"\"%')",
        note="blocking: a dose without a unit cannot be calculated")

    # INV-08 — version >= 1
    add("INV-08", "Every object has version >= 1", True,
        "SELECT id FROM objects WHERE version IS NULL OR version < 1")

    # INV-09 — normalized DRUG preserves original wording (scoped to Medication objects only)
    add("INV-09", "Normalized drug preserves original_text", True,
        "SELECT p.obj_id FROM provenance p JOIN objects o ON o.id=p.obj_id "
        "WHERE o.type='Medication' AND p.normalized_value IS NOT NULL AND p.normalized_value != '' "
        "AND (p.original_text IS NULL OR p.original_text='')")

    # INV-12 — status in allowed set
    placeholders = ",".join("'%s'" % s for s in ALLOWED_STATUSES)
    add("INV-12", "Status is an allowed lifecycle state", True,
        f"SELECT id FROM objects WHERE status NOT IN ({placeholders})")

    # INV-10 — monotonic versions: no two active objects share id with same version dup
    add("INV-10", "No duplicate (id, version) rows", True,
        "SELECT id FROM objects GROUP BY id, version HAVING COUNT(*) > 1")

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"DB not found: {db}")
        raise SystemExit(2)

    # read-only connection (safe to run while a writer is active)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    results = check(conn)
    conn.close()

    blocking_failures = [r for r in results if r.blocking and not r.passed]

    print(f"\n=== ARCHITECTURAL INVARIANTS — {db.name} ===")
    for r in results:
        tag = "PASS" if r.passed else ("FAIL" if r.blocking else "warn")
        extra = f" (sample: {', '.join(r.sample)})" if r.sample else ""
        note = f"  [{r.note}]" if r.note else ""
        print(f"  [{tag}] {r.id} {r.name}: {r.violations} violation(s){extra}{note}")

    print(f"\nblocking failures: {len(blocking_failures)}")
    if args.json:
        Path(args.json).write_text(json.dumps(
            [r.__dict__ for r in results], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report: {args.json}")

    raise SystemExit(1 if blocking_failures else 0)


if __name__ == "__main__":
    main()
