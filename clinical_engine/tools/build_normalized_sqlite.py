"""Build a real normalized_regimens SQLite from metadata.sqlite antibiotic_regimens.

The Engine reads the `normalized_regimens` table (via NormalizerDB). The
production metadata.sqlite only holds the raw `antibiotic_regimens` KB, so
this tool runs the FROZEN MedicalNormalizer over all 2675 raw regimens and
persists them, producing a DB the Engine can query end-to-end.

guideline_id := clinrec_id, regimen_id := antibiotic_regimens.id — the same
keys the draft diagnosis_index.json uses, so DiagnosisMatch -> RegimenLoad
line up.

Usage (from repo root):
    python -m clinical_engine.tools.build_normalized_sqlite \
        [--src C:/clinrec_downloader/metadata.sqlite] \
        [--out C:/clinrec_downloader/normalized_regimens.sqlite]
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

from medical_normalizer.db import NormalizerDB
from medical_normalizer.normalizer import MedicalNormalizer

_DEFAULT_SRC = r"C:\clinrec_downloader\metadata.sqlite"
_DEFAULT_OUT = r"C:\clinrec_downloader\normalized_regimens.sqlite"


def _raw_of(row: sqlite3.Row) -> dict:
    return {
        "antibiotic": row["antibiotic"],
        "dose": row["dose"],
        "unit": row["unit"],
        "route": row["route"],
        "frequency": row["frequency"],
        "duration": row["duration"],
        "age_group": row["age_group"],
        "regimen_type": row["regimen_type"],
        "pregnancy": row["pregnancy"],
        "renal_adjustment": row["renal_adjustment"],
    }


def build(src: str, out: str) -> dict:
    out_path = Path(out)
    if out_path.exists():
        out_path.unlink()  # rebuild fresh

    src_db = sqlite3.connect(src)
    src_db.row_factory = sqlite3.Row
    rows = src_db.execute("SELECT * FROM antibiotic_regimens").fetchall()
    src_db.close()

    db = NormalizerDB.connect(out)
    start = time.perf_counter()
    saved = 0
    try:
        for row in rows:
            result = MedicalNormalizer.normalize(_raw_of(row))
            db.save(
                result,
                guideline_id=str(row["clinrec_id"]),
                regimen_id=str(row["id"]),
                source_pdf=row["pdf_file"] or "",
                source_page=str(row["page_number"] or ""),
                source_quote=row["source_quote"] or "",
                diagnosis=row["diagnosis"] or "",
                mkb=row["mkb"] or "",
            )
            saved += 1
        stats = db.stats()
    finally:
        db.close()
    elapsed = time.perf_counter() - start
    return {"out": out, "saved": saved, "elapsed_s": elapsed, "stats": stats}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=_DEFAULT_SRC)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    args = ap.parse_args()
    r = build(args.src, args.out)
    print("=== normalized_regimens.sqlite built ===")
    print(f"out:      {r['out']}")
    print(f"saved:    {r['saved']} regimens in {r['elapsed_s']:.2f}s")
    print(f"stats:    {r['stats']}")


if __name__ == "__main__":
    main()
