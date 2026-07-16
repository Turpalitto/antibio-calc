"""Generates evidence/regimen_5574_verified_evidence.json by directly querying
the real, read-only sources — no hand-typed content anywhere in this script's
output. Run: python evidence/generate_regimen_5574_evidence.py

This exists specifically to prevent a repeat of the RC-031 false finding,
where a hand-written "database quote" was presented as if it were captured
query output. Every EvidenceBlock below is built from an actual query result
or actual extracted PDF text, never from a string literal describing what the
source "should" contain.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dose_verification_sandbox.evidence_model import EvidenceBlock, build_packet, render_markdown

ASSEMBLED_DB = REPO_ROOT / "assembled_regimens.sqlite"
NORMALIZED_DB = REPO_ROOT / "backups" / "p5_6_baseline_20260715" / "normalized_regimens.sqlite"
PDF_PATH = Path("C:/clinrec_downloader/downloads_active/Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf")

REGIMEN_ID = "5574"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_evidence() -> list[EvidenceBlock]:
    blocks: list[EvidenceBlock] = []
    now = _now()

    # --- assembled_regimens.sqlite ---
    assembled_hash = _sha256_file(ASSEMBLED_DB)
    query1 = f"SELECT * FROM assembled_regimens WHERE regimen_id='{REGIMEN_ID}'"
    conn = sqlite3.connect(f"file:{ASSEMBLED_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query1)
    row = dict(cur.fetchone())
    conn.close()
    blocks.append(EvidenceBlock(
        evidence_origin="DATABASE_QUERY", source_artifact="assembled_regimens.sqlite",
        source_hash=assembled_hash, retrieval_command=query1, retrieved_at=now,
        record_identifier=f"assembled_regimens:{REGIMEN_ID}:{row.get('version')}",
        is_exact=True, content=json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True),
    ))

    # --- normalized_regimens.sqlite (upstream) ---
    normalized_hash = _sha256_file(NORMALIZED_DB)
    query2 = f"SELECT * FROM normalized_regimens WHERE regimen_id='{REGIMEN_ID}'"
    conn2 = sqlite3.connect(f"file:{NORMALIZED_DB.as_posix()}?mode=ro", uri=True)
    conn2.row_factory = sqlite3.Row
    cur2 = conn2.cursor()
    cur2.execute(query2)
    nrow = dict(cur2.fetchone())
    conn2.close()
    blocks.append(EvidenceBlock(
        evidence_origin="DATABASE_QUERY", source_artifact="normalized_regimens.sqlite",
        source_hash=normalized_hash, retrieval_command=query2, retrieved_at=now,
        record_identifier=f"normalized_regimens:{REGIMEN_ID}",
        is_exact=True, content=json.dumps(nrow, ensure_ascii=False, indent=2, sort_keys=True),
    ))

    # --- source PDF ---
    if PDF_PATH.exists():
        pdf_hash = _sha256_file(PDF_PATH)
        import fitz
        doc = fitz.open(str(PDF_PATH))
        page_text = doc[15].get_text()  # page 16, 0-indexed
        doc.close()
        blocks.append(EvidenceBlock(
            evidence_origin="SOURCE_PDF_EXTRACT", source_artifact=PDF_PATH.name,
            source_hash=pdf_hash, retrieval_command="fitz.open(path).load_page(15).get_text()",
            retrieved_at=now, record_identifier=f"{PDF_PATH.name}:page16",
            is_exact=True, content=page_text,
        ))
    else:
        blocks.append(EvidenceBlock(
            evidence_origin="HUMAN_NOTE", source_artifact="none",
            source_hash=None, retrieval_command=None, retrieved_at=now,
            record_identifier="pdf-unavailable",
            is_exact=False, content=f"PDF not found at {PDF_PATH} at generation time",
        ))

    # --- computed comparison (derived from the two DATABASE_QUERY blocks above, not hand-typed) ---
    drug_match = row.get("antibiotic") == nrow.get("drug_normalized")
    dose_match = row.get("dose") == nrow.get("dose") and row.get("unit") == nrow.get("dose_unit")
    inputs_hash = hashlib.sha256(
        json.dumps([row, nrow], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    blocks.append(EvidenceBlock(
        evidence_origin="GENERATED_CALCULATION", source_artifact="evidence_model.py comparison",
        source_hash=inputs_hash, retrieval_command="row['antibiotic']==nrow['drug_normalized']; "
                                             "row['dose']==nrow['dose'] and row['unit']==nrow['dose_unit']",
        retrieved_at=now, record_identifier="assembled-vs-normalized-consistency",
        is_exact=True,
        content=json.dumps({
            "assembled_antibiotic": row.get("antibiotic"),
            "normalized_drug_normalized": nrow.get("drug_normalized"),
            "drug_name_consistent": drug_match,
            "assembled_dose": [row.get("dose"), row.get("unit")],
            "normalized_dose": [nrow.get("dose"), nrow.get("dose_unit")],
            "dose_consistent": dose_match,
        }, ensure_ascii=False, indent=2),
    ))

    return blocks


def main() -> None:
    blocks = build_evidence()
    packet = build_packet(blocks, meta={
        "subject": f"regimen_id={REGIMEN_ID}",
        "generated_at": _now(),
        "generator": "evidence/generate_regimen_5574_evidence.py",
        "purpose": "Post-RC-031 evidence-integrity hardening: machine-generated, hash-verifiable "
                   "evidence packet replacing the hand-typed comparison that produced the false finding.",
    })
    out_dir = Path(__file__).parent
    out_json = out_dir / "regimen_5574_verified_evidence.json"
    out_json.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    report_md = render_markdown(packet, title="REGIMEN 5574 VERIFICATION REPORT")
    (REPO_ROOT / "REGIMEN_5574_VERIFICATION_REPORT.md").write_text(report_md, encoding="utf-8")

    print(f"Evidence packet: {out_json}")
    print(f"Report: {REPO_ROOT / 'REGIMEN_5574_VERIFICATION_REPORT.md'}")
    print(f"packet_hash: {packet['packet_hash']}")


if __name__ == "__main__":
    main()
