"""Build a DRAFT diagnosis_index.json from metadata.sqlite (antibiotic_regimens).

Status of the output: AUTO_GENERATED_DRAFT — this is a mechanical extraction
from the extracted knowledge base, NOT a clinically curated routing table.
It preserves diagnosis / ICD-10 / guideline_id exactly as stored and never
resolves conflicts.

Usage (from repo root):
    python -m clinical_engine.tools.build_diagnosis_index_draft \
        [--sqlite C:/clinrec_downloader/metadata.sqlite] \
        [--out clinical_engine/resources/diagnosis_index.json]

Prints a generation report (total entries, unique guideline_ids, duplicate
diagnoses, conflicting mappings, missing ICD-10, empty diagnosis names).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_SQLITE = r"C:\clinrec_downloader\metadata.sqlite"
_DEFAULT_OUT = "clinical_engine/resources/diagnosis_index.json"
_YEAR_RE = re.compile(r"(19|20)\d{2}")


def _split_icd10(mkb: str | None) -> tuple[str, ...]:
    """Parse the stored mkb field into ICD-10 codes.

    Deterministic parsing only (no heuristics): mkb is stored in two forms —
    comma/semicolon-separated ("A30, B92") or a JSON-array string
    ('["M08.1", "M08.3"]'). Both are unambiguous. Strip stray
    brackets/quotes/whitespace so the same code compares equal regardless of
    stored form.
    """
    if not mkb:
        return ()
    s = mkb.strip()
    codes: list[str] = []
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                codes = [str(x) for x in parsed]
        except json.JSONDecodeError:
            codes = []
    if not codes:
        codes = re.split(r"[;,]", s)
    cleaned = []
    for c in codes:
        c = c.strip().strip("[]\"'").strip()
        if c:
            cleaned.append(c)
    return tuple(cleaned)


def _year_of(publication_date: str | None) -> int | None:
    if not publication_date:
        return None
    m = _YEAR_RE.search(publication_date)
    return int(m.group(0)) if m else None


def build(sqlite_path: str, out_path: str) -> dict:
    db = sqlite3.connect(sqlite_path)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT DISTINCT clinrec_id, diagnosis, mkb, clinrec_name, publication_date "
        "FROM antibiotic_regimens"
    ).fetchall()
    db.close()

    # One entry per distinct (guideline_id, diagnosis, mkb) tuple — preserve
    # exactly as stored, resolve nothing.
    seen: set[tuple[str, str, str]] = set()
    entries: list[dict] = []
    for r in rows:
        guideline_id = str(r["clinrec_id"]) if r["clinrec_id"] is not None else ""
        diagnosis = (r["diagnosis"] or "").strip()
        mkb = (r["mkb"] or "").strip()
        key = (guideline_id, diagnosis, mkb)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "guideline_id": guideline_id,
                "diagnosis_name": diagnosis,
                "icd10_codes": list(_split_icd10(mkb)),
                "guideline_title": (r["clinrec_name"] or "").strip(),
                "guideline_year": _year_of(r["publication_date"]),
                "guideline_revision_date": (r["publication_date"] or None),
                "source_url": "",  # not fabricated — left blank in the draft
            }
        )

    entries.sort(key=lambda e: (e["guideline_id"], e["diagnosis_name"]))
    report = _report(entries)

    doc = {
        "meta": {
            "status": "AUTO_GENERATED_DRAFT",
            "warning": (
                "Mechanically extracted from metadata.sqlite antibiotic_regimens. "
                "NOT clinically curated. Diagnosis/ICD-10/guideline_id preserved "
                "exactly as stored; conflicts NOT resolved. Requires human review "
                "before any clinical/production use."
            ),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": f"{sqlite_path} :: antibiotic_regimens",
            "guideline_set_version": "draft-auto",
            "generation_report": report,
        },
        "entries": entries,
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"out": str(out), "report": report}


def _report(entries: list[dict]) -> dict:
    total = len(entries)
    unique_guidelines = len({e["guideline_id"] for e in entries})

    dx_to_guidelines: dict[str, set[str]] = defaultdict(set)
    dx_count: dict[str, int] = defaultdict(int)
    for e in entries:
        dx_to_guidelines[e["diagnosis_name"]].add(e["guideline_id"])
        dx_count[e["diagnosis_name"]] += 1

    duplicate_diagnoses = sorted(
        [dx for dx, c in dx_count.items() if c > 1 and dx],
    )
    # Conflicting mappings: the SAME diagnosis text routing to MULTIPLE distinct
    # guideline_ids (ambiguous routing — a lookup would return several).
    conflicting = {
        dx: sorted(gids)
        for dx, gids in dx_to_guidelines.items()
        if dx and len(gids) > 1
    }
    missing_icd10 = sum(1 for e in entries if not e["icd10_codes"])
    empty_diagnosis = sum(1 for e in entries if not e["diagnosis_name"])

    return {
        "total_entries": total,
        "unique_guideline_ids": unique_guidelines,
        "duplicate_diagnosis_names": len(duplicate_diagnoses),
        "conflicting_mappings": len(conflicting),
        "missing_icd10_entries": missing_icd10,
        "empty_diagnosis_entries": empty_diagnosis,
        "conflicting_examples": dict(list(conflicting.items())[:10]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default=_DEFAULT_SQLITE)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    args = ap.parse_args()
    result = build(args.sqlite, args.out)
    r = result["report"]
    print("=== diagnosis_index.json — AUTO_GENERATED_DRAFT ===")
    print(f"written: {result['out']}")
    print(f"total entries:            {r['total_entries']}")
    print(f"unique guideline_ids:     {r['unique_guideline_ids']}")
    print(f"duplicate diagnosis names:{r['duplicate_diagnosis_names']}")
    print(f"conflicting mappings:     {r['conflicting_mappings']}")
    print(f"missing ICD-10 entries:   {r['missing_icd10_entries']}")
    print(f"empty diagnosis entries:  {r['empty_diagnosis_entries']}")
    if r["conflicting_examples"]:
        print("--- conflicting examples (diagnosis -> guideline_ids) ---")
        for dx, gids in r["conflicting_examples"].items():
            print(f"  {dx[:60]!r} -> {gids}")


if __name__ == "__main__":
    main()
