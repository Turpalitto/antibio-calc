#!/usr/bin/env python
"""
Knowledge Coverage Report (delivered coverage) — ANTIBIO.

Distinct from CKY (acceptance ratio). Coverage answers "what does the system deliver, across how
much of the corpus?" — per clinical dimension, the fraction of source guidelines/PDFs for which at
least one accepted Knowledge Object of that dimension exists in the KB.

    Delivered Coverage[dim] = (# distinct source PDFs with >=1 object of dim) / (# distinct PDFs)

Pure read-only SQL over a KB db; cheap; safe to run against the full corpus KB (including while a
writer is active). Recognition coverage (capability breadth) comes from semantic_yield_audit.py.

Usage:
    python -m src.pipeline.knowledge_coverage --db kb_p44.db
    python -m src.pipeline.knowledge_coverage --db kb_p44.db --json coverage.json

Note: the current KB stores coarse object types (Medication/Dose/Contraindication/Evidence/
Diagnosis/Recommendation). Fine dimensions (alternatives/first_line/pediatric/pregnancy/renal) are
reported from provenance/subtype hints where available; where a dimension has no representation in
the KB schema yet, its coverage is 0.0 by construction — which is itself the finding (e.g. RC-009).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

# Map a coverage dimension to a SQL predicate over objects o (+ provenance p) identifying it.
DIMENSIONS = {
    "drug":              "o.type='Medication'",
    "dose":              "o.type='Dose' AND o.content LIKE '%\"subtype\": \"Dose\"%'",
    "duration":          "o.content LIKE '%\"subtype\": \"Duration\"%'",
    "frequency":         "o.content LIKE '%\"subtype\": \"Frequency\"%'",
    "route":             "o.content LIKE '%\"subtype\": \"Route\"%'",
    "contraindications": "o.type='Contraindication'",
    "evidence":          "o.type='Evidence'",
    "diagnosis":         "o.type='Diagnosis'",
    # Fine safety/therapy dimensions — currently no dedicated KB type (tracked: RC-009).
    "alternatives":      "o.content LIKE '%alternative%'",
    "first_line":        "o.content LIKE '%first_line%'",
    "pediatric":         "o.content LIKE '%pediatric%' OR o.content LIKE '%мг/кг%'",
    "pregnancy":         "o.content LIKE '%pregnan%' OR o.content LIKE '%беремен%'",
    "renal":             "o.content LIKE '%renal%' OR o.content LIKE '%почеч%'",
}


def coverage(db: Path):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    total_pdfs = conn.execute("SELECT COUNT(DISTINCT pdf) FROM provenance").fetchone()[0] or 0
    rows = {}
    for dim, pred in DIMENSIONS.items():
        n = conn.execute(
            f"SELECT COUNT(DISTINCT p.pdf) FROM objects o JOIN provenance p ON p.obj_id=o.id "
            f"WHERE {pred}").fetchone()[0]
        rows[dim] = {"pdfs_with_dim": n, "total_pdfs": total_pdfs,
                     "coverage_pct": round(100 * n / total_pdfs, 1) if total_pdfs else None}
    conn.close()
    return total_pdfs, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    db = Path(args.db)
    if not db.exists():
        print(f"DB not found: {db}")
        raise SystemExit(2)

    total, rows = coverage(db)
    print(f"\n=== KNOWLEDGE COVERAGE (delivered) — {db.name} ===")
    print(f"corpus: {total} distinct source PDFs\n")
    for dim, v in sorted(rows.items(), key=lambda kv: (kv[1]["coverage_pct"] or 0), reverse=True):
        pct = v["coverage_pct"]
        bar = "#" * int((pct or 0) / 2.5)
        print(f"  {dim:20s} {str(pct)+'%':>7s}  ({v['pdfs_with_dim']}/{v['total_pdfs']})  {bar}")
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"total_pdfs": total, "dimensions": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nreport: {args.json}")


if __name__ == "__main__":
    main()
