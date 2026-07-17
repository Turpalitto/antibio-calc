"""RC-030 C6.7 Part III — build the exact 117-candidate manifest.

Read-only. Joins the frozen 365-record replay classification
(`generated/rc030_multiworkstream/replay_with_unit_fix_365.json`) against
`assembled_regimens.sqlite` (source_pdf/page/quote/clinical fields) and
`CORPUS_MANIFEST.json` (expected PDF sha256), then re-runs the committed,
already-tested `dose_verification_sandbox.span_attribution.attribute()` on
each record's own source_quote to recover span offsets, competing
candidates, and score components deterministically (no re-derivation of
the classification decision itself is attempted here -- the frozen
classification from the replay artifact is treated as authoritative and
is *compared* against a fresh re-run for a repeat-determinism check).

No database is written. No PDF is opened (PDF hash verification is
against the already-recorded corpus manifest hash, not a fresh read of
the PDF bytes -- a fresh byte-for-byte re-hash of all 117 source PDFs is
Part VII, not this script).

Every emitted record is unconditionally marked:
    clinically_approved = false
    calculation_eligibility = "BLOCKED"
    authoritative_migration_allowed = false
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dose_verification_sandbox.span_attribution import (  # noqa: E402
    attribute, normalize_text,
)

ROOT = Path(__file__).resolve().parents[2]
REPLAY_PATH = ROOT / "generated" / "rc030_multiworkstream" / "replay_with_unit_fix_365.json"
DB_PATH = ROOT / "assembled_regimens.sqlite"
MANIFEST_PATH = ROOT / "CORPUS_MANIFEST.json"
OUT_PATH = ROOT / "generated" / "rc030_c67" / "candidate_117_manifest.json"

COLUMNS = [
    "regimen_id", "version", "status", "diagnosis", "age_group", "route",
    "frequency", "duration_recommended", "antibiotic", "dose", "unit",
    "source_pdf", "source_page", "source_quote", "validation_verdict",
    "confidence", "review_status", "needs_review_reasons",
]


def load_replay() -> list[dict]:
    data = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    return data["results"]


def load_pdf_hash_index() -> dict[str, str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    index: dict[str, str] = {}
    for doc in manifest["documents"]:
        fname = doc["file"]
        index[fname] = doc["sha256"]
        # also index by basename of any source_locations path, for robustness
        for loc in doc.get("source_locations", []):
            index[Path(loc).name] = doc["sha256"]
    return index


def fetch_regimen_rows(con: sqlite3.Connection, ids: list[tuple[str, int]]) -> dict[tuple[str, int], dict]:
    cur = con.cursor()
    cols_sql = ", ".join(COLUMNS)
    out: dict[tuple[str, int], dict] = {}
    for rid, ver in ids:
        cur.execute(
            f"SELECT {cols_sql} FROM assembled_regimens WHERE regimen_id = ? AND version = ?",
            (rid, ver),
        )
        row = cur.fetchone()
        if row is None:
            continue
        out[(rid, ver)] = dict(zip(COLUMNS, row))
    return out


def build() -> dict:
    results = load_replay()
    candidates = [r for r in results if r["classification"] in ("SAFE_EXACT_LINK", "SAFE_SINGLE_CANDIDATE")]
    assert len(candidates) == 117, f"expected 117 candidates, got {len(candidates)}"

    ids = [(r["regimen_id"], r["regimen_version"]) for r in candidates]
    assert len(set(ids)) == len(ids), "duplicate (regimen_id, version) in candidate pool"

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = fetch_regimen_rows(con, ids)
    pdf_hash_index = load_pdf_hash_index()

    manifest_records = []
    integrity_issues = []

    for cand in candidates:
        key = (cand["regimen_id"], cand["regimen_version"])
        row = rows.get(key)
        record = {
            "regimen_id": cand["regimen_id"],
            "regimen_version": cand["regimen_version"],
            "frozen_classification": cand["classification"],
            "frozen_dose_min": cand.get("dose_min"),
            "frozen_dose_max": cand.get("dose_max"),
            "old_trust": cand.get("old_trust"),
        }
        if row is None:
            record["integrity_status"] = "SOURCE_ROW_MISSING"
            integrity_issues.append({"key": key, "issue": "assembled_regimens row not found"})
            manifest_records.append(record)
            continue

        source_pdf = row["source_pdf"]
        expected_hash = pdf_hash_index.get(source_pdf)

        record.update({
            "expected_antibiotic": row["antibiotic"],
            "structured_dose": row["dose"],
            "structured_unit": row["unit"],
            "route": row["route"],
            "age_group": row["age_group"],
            "frequency": row["frequency"],
            "duration_recommended": row["duration_recommended"],
            "diagnosis": row["diagnosis"],
            "source_pdf": source_pdf,
            "source_page": row["source_page"],
            "source_quote": row["source_quote"],
            "pdf_manifest_sha256": expected_hash,
            "pdf_manifest_lookup": "FOUND" if expected_hash else "NOT_FOUND_IN_CORPUS_MANIFEST",
            "assembled_validation_verdict": row["validation_verdict"],
            "assembled_review_status": row["review_status"],
            "assembled_needs_review_reasons": row["needs_review_reasons"],
        })

        # deterministic repeat: re-run attribute() on this record's own quote
        table_flag = bool(row["needs_review_reasons"]) and "table" in (row["needs_review_reasons"] or "").lower()
        norm = normalize_text(row["source_quote"] or "")
        result = attribute(
            normalized=norm.normalized,
            known_antibiotic_raw=row["antibiotic"],
            current_scalar=row["dose"],
            current_unit=row["unit"],
            table_context=table_flag,
        )
        record["repeat_classification"] = result.classification
        record["repeat_matches_frozen"] = (result.classification == cand["classification"])
        if not record["repeat_matches_frozen"]:
            integrity_issues.append({
                "key": key,
                "issue": f"repeat classification {result.classification} != frozen {cand['classification']}",
            })

        if result.selected_range is not None:
            raw_start, raw_end = norm.raw_span(result.selected_range.start, result.selected_range.end)
            record["selected_range_span"] = {
                "normalized_start": result.selected_range.start,
                "normalized_end": result.selected_range.end,
                "raw_start": raw_start,
                "raw_end": raw_end,
                "raw_text": result.selected_range.raw_text,
                "lower": result.selected_range.lower,
                "upper": result.selected_range.upper,
                "unit_raw": result.selected_range.unit_raw,
            }
            if not (result.selected_range.lower < result.selected_range.upper):
                integrity_issues.append({"key": key, "issue": "non-increasing range bounds"})
        else:
            record["selected_range_span"] = None
            integrity_issues.append({"key": key, "issue": "repeat run produced no selected_range"})

        if result.selected_antibiotic is not None:
            raw_start, raw_end = norm.raw_span(result.selected_antibiotic.start, result.selected_antibiotic.end)
            record["antibiotic_span"] = {
                "normalized_start": result.selected_antibiotic.start,
                "normalized_end": result.selected_antibiotic.end,
                "raw_start": raw_start,
                "raw_end": raw_end,
                "canonical": result.selected_antibiotic.canonical,
                "raw_token": result.selected_antibiotic.raw_token,
            }
        else:
            record["antibiotic_span"] = None

        record["competing_ranges_count"] = len(result.competing_ranges)
        record["score_components"] = result.score_components
        record["table_context_flag_used"] = table_flag

        if expected_hash is None:
            record["integrity_status"] = "PDF_NOT_IN_MANIFEST"
            integrity_issues.append({"key": key, "issue": f"source_pdf {source_pdf!r} not found in CORPUS_MANIFEST.json"})
        elif not record["repeat_matches_frozen"]:
            record["integrity_status"] = "CLASSIFICATION_REPEAT_MISMATCH"
        else:
            record["integrity_status"] = "OK"

        # governance flags -- unconditional
        record["owner_review_required"] = True
        record["clinically_approved"] = False
        record["calculation_eligibility"] = "BLOCKED"
        record["authoritative_migration_allowed"] = False

        manifest_records.append(record)

    exact = [r for r in manifest_records if r["frozen_classification"] == "SAFE_EXACT_LINK"]
    single = [r for r in manifest_records if r["frozen_classification"] == "SAFE_SINGLE_CANDIDATE"]

    out = {
        "schema_version": 1,
        "total": len(manifest_records),
        "safe_exact_link_count": len(exact),
        "safe_single_candidate_count": len(single),
        "integrity_issues_count": len(integrity_issues),
        "integrity_issues": integrity_issues,
        "records": manifest_records,
    }
    return out


def main() -> None:
    out = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")
    print(f"total={out['total']} exact={out['safe_exact_link_count']} single={out['safe_single_candidate_count']} "
          f"integrity_issues={out['integrity_issues_count']}")
    print(f"written to {OUT_PATH}")


if __name__ == "__main__":
    main()
