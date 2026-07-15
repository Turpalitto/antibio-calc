"""Phase 3 — Read-only export from assembled_regimens.sqlite.

Opens the source database strictly read-only (SQLite URI mode=ro) and writes a
versioned JSON snapshot grouped by diagnosis -> antibiotic -> regimen variants.
Never writes to assembled_regimens.sqlite or any other source database.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SOURCE_DB = "assembled_regimens.sqlite"
DATA_DIR = Path(__file__).parent / "data"


def _connect_readonly(db_path: str) -> sqlite3.Connection:
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def export_snapshot(source_db: str = SOURCE_DB, out_dir: Path = DATA_DIR) -> Path:
    conn = _connect_readonly(source_db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM assembled_regimens ORDER BY icd_mkb, diagnosis, antibiotic, regimen_id")
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    diagnoses: dict[str, dict[str, Any]] = {}
    for row in rows:
        icd = row.get("icd_mkb") or "UNSPECIFIED"
        diag_display = row.get("diagnosis") or ""
        key = icd
        d = diagnoses.setdefault(key, {
            "diagnosis_code": icd,
            "diagnosis_display": diag_display,
            "antibiotics": {},
        })
        # keep the longest/most informative display text seen for this code
        if len(diag_display) > len(d["diagnosis_display"]):
            d["diagnosis_display"] = diag_display

        abx = row.get("antibiotic") or "UNSPECIFIED"
        a = d["antibiotics"].setdefault(abx, {"antibiotic_name": abx, "regimens": []})

        try:
            field_provenance = json.loads(row.get("field_provenance") or "[]")
        except (TypeError, ValueError):
            field_provenance = []
        try:
            needs_review_reasons = json.loads(row.get("needs_review_reasons") or "[]")
        except (TypeError, ValueError):
            needs_review_reasons = []
        try:
            contraindications = json.loads(row.get("contraindications") or "[]")
        except (TypeError, ValueError):
            contraindications = []

        a["regimens"].append({
            "regimen_id": row.get("regimen_id"),
            "version": row.get("version"),
            "status": row.get("status"),
            "review_status": row.get("review_status"),
            "approved_by": row.get("approved_by") or None,
            "approved_at": row.get("approved_at") or None,
            "validation_verdict": row.get("validation_verdict"),
            "confidence": row.get("confidence"),
            "antibiotic": abx,
            "dose": row.get("dose"),
            "unit": row.get("unit"),
            "frequency": row.get("frequency"),
            "duration_recommended": row.get("duration_recommended"),
            "route": row.get("route"),
            "age_group": row.get("age_group"),
            "pregnancy": row.get("pregnancy"),
            "renal_adjustment": row.get("renal_adjustment"),
            "therapy_line": row.get("therapy_line"),
            "guideline_id": row.get("guideline_id"),
            "evidence_level": row.get("evidence_level"),
            "contraindications": contraindications,
            "source_pdf": row.get("source_pdf"),
            "source_page": row.get("source_page"),
            "source_quote": row.get("source_quote"),
            "field_provenance": field_provenance,
            "needs_review_reasons": needs_review_reasons,
            "snapshot_version": row.get("snapshot_version"),
            "assembly_ruleset_version": row.get("assembly_ruleset_version"),
            "created_at": row.get("created_at"),
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    exported_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {
        "meta": {
            "exported_at": exported_at,
            "source_db": source_db,
            "source_table": "assembled_regimens",
            "row_count": len(rows),
            "label": "QA / RESEARCH ONLY — NOT CLINICALLY APPROVED — DO NOT USE FOR PATIENT CARE",
            "note": "Every regimen below is, at best, REVIEW_REQUIRED. No APPROVED regimens exist in the source data as of export time.",
        },
        "diagnoses": list(diagnoses.values()),
    }

    out_path = out_dir / "snapshot_latest.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    path = export_snapshot()
    print(f"Snapshot written to {path}")
