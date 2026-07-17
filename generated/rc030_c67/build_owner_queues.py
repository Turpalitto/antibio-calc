"""RC-030 C6.7 Part X — build the two governed owner-review queues
(QUEUE A: retained exact-link confirmation, QUEUE B: single-candidate
review) in the existing C4/C5-compatible record schema
(owner_review_data.json shape), plus a separate AI-pre-review companion
file kept out of the owner-facing datasets entirely (Part XI /
Phase 19: AI conclusions must never be preloaded where the owner can see
them before submitting).

Read-only against source data; writes only under generated/rc030_c67/.
No DB write. No owner_verdict/canonical_verdict/ui_action key is ever
placed in the owner-facing datasets (build_interface.py itself refuses
those keys at build time -- this script also never emits them by
construction).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dose_verification_sandbox.pdf_evidence import find_quote_in_page_text, normalize_whitespace  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "generated" / "rc030_c67" / "candidate_117_manifest.json"
EXACT_DISP_PATH = ROOT / "generated" / "rc030_c67" / "exact_link_disposition.json"
SINGLE_DISP_PATH = ROOT / "generated" / "rc030_c67" / "single_candidate_disposition.json"
PASS_A_PATH = ROOT / "generated" / "rc030_c67" / "pass_a_output.json"
PDF_HASH_PATH = ROOT / "generated" / "rc030_c67" / "pdf_hash_reverify.json"

OUT_A = ROOT / "RC030_C67_EXACT_LINK_OWNER_QUEUE.json"
OUT_B = ROOT / "RC030_C67_SINGLE_CANDIDATE_OWNER_QUEUE.json"
OUT_AI = ROOT / "generated" / "rc030_c67" / "ai_pre_review_companion.json"

ASSEMBLED_SHA = "9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9"

FORBIDDEN_KEYS = {"owner_verdict", "canonical_verdict", "ui_action", "human_fidelity_verdict"}


def compute_evidence_hash(rec: dict) -> str:
    payload = json.dumps(
        {"regimen_id": rec["regimen_id"], "regimen_version": rec["regimen_version"],
         "source_pdf": rec["source_pdf"], "source_page": rec["source_page"],
         "source_quote": rec["source_quote"]},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    exact_disp = json.loads(EXACT_DISP_PATH.read_text(encoding="utf-8"))
    single_disp = json.loads(SINGLE_DISP_PATH.read_text(encoding="utf-8"))
    pass_a = {(v["regimen_id"], str(v["regimen_version"])): v
              for v in json.loads(PASS_A_PATH.read_text(encoding="utf-8"))}
    pdf_hash_check = json.loads(PDF_HASH_PATH.read_text(encoding="utf-8"))
    path_by_file = {r["file"]: r.get("path") for r in pdf_hash_check["results"]
                    if r["status"] == "PDF_EVIDENCE_VALID"}

    pdf_cache: dict[str, "fitz.Document"] = {}

    def get_context(source_pdf: str, source_page: str, quote: str) -> tuple[str, str]:
        path = path_by_file.get(source_pdf)
        if not path:
            return "", ""
        if path not in pdf_cache:
            pdf_cache[path] = fitz.open(path)
        doc = pdf_cache[path]
        try:
            page_num = int(source_page) - 1
        except (TypeError, ValueError):
            return "", ""
        if page_num < 0 or page_num >= doc.page_count:
            return "", ""
        page_text = doc[page_num].get_text()
        norm_page = normalize_whitespace(page_text)
        norm_quote = normalize_whitespace(quote or "")
        idx = find_quote_in_page_text(page_text, quote or "")
        if idx == -1:
            return "", ""
        before = norm_page[max(0, idx - 200):idx]
        after = norm_page[idx + len(norm_quote):idx + len(norm_quote) + 200]
        return before, after

    queue_a_records = []
    queue_b_records = []
    ai_companion = []
    evidence_hashes_seen = set()

    for r in manifest["records"]:
        rid = r["regimen_id"]
        ver = r["regimen_version"]
        key = (rid, str(ver))
        frozen = r["frozen_classification"]

        base = {
            "regimen_id": rid,
            "regimen_version": ver,
            "antibiotic": r["expected_antibiotic"],
            "diagnosis": r["diagnosis"],
            "age_group": r["age_group"],
            "dose": r["structured_dose"],
            "unit": r["structured_unit"],
            "frequency": r["frequency"],
            "route": r["route"],
            "duration_recommended": r["duration_recommended"],
            "source_pdf": r["source_pdf"],
            "source_page": r["source_page"],
            "source_quote": r["source_quote"],
            "pdf_hash": r["pdf_manifest_sha256"],
            "calculation_eligibility": "BLOCKED",
            "clinically_approved": False,
            "authoritative_migration_allowed": False,
        }
        before, after = get_context(r["source_pdf"], r["source_page"], r["source_quote"])
        base["context_before"] = before
        base["context_after"] = after
        base["evidence_hash"] = compute_evidence_hash(base)
        assert base["evidence_hash"] not in evidence_hashes_seen, f"duplicate evidence_hash for {rid}"
        evidence_hashes_seen.add(base["evidence_hash"])
        assert not (FORBIDDEN_KEYS & base.keys())

        if frozen == "SAFE_EXACT_LINK":
            disp = exact_disp[rid]
            if disp != "EXACT_LINK_RETAINED":
                continue  # QUEUE A only contains retained exact links
            queue_a_records.append(base)
        else:
            disp = single_disp[rid]
            entry = dict(base)
            entry["review_reason_group"] = disp
            queue_b_records.append(entry)

        # AI pre-review companion -- kept OUT of the owner-facing queues entirely
        pa = pass_a.get(key, {})
        ai_companion.append({
            "regimen_id": rid, "regimen_version": ver,
            "evidence_hash": base["evidence_hash"],
            "review_origin": "AI_PRE_REVIEW",
            "engine_classification": frozen,
            "engine_disposition": disp,
            "pass_a_verdict": pa.get("verdict"),
            "pass_a_confidence": pa.get("confidence"),
            "pass_a_rationale": pa.get("rationale"),
            "owner_verified": False,
            "clinically_approved": False,
            "calculation_eligibility": "BLOCKED",
        })

    queue_a_records.sort(key=lambda r: (r["regimen_id"], r["regimen_version"]))
    queue_b_records.sort(key=lambda r: (r["review_reason_group"], r["regimen_id"], r["regimen_version"]))

    out_a = {
        "schema_version": 1,
        "queue": "EXACT_LINK_CONFIRMATION",
        "generated_from": {"assembled_regimens_sha256": ASSEMBLED_SHA, "candidate_manifest": "generated/rc030_c67/candidate_117_manifest.json"},
        "queue_size": len(queue_a_records),
        "selection_criteria": "EXACT_LINK_RETAINED disposition only (Part V of RC030_C67_DOUBLE_PASS_REPORT.md) -- no preselected verdict, no AI conclusion embedded.",
        "records": queue_a_records,
    }
    out_b = {
        "schema_version": 1,
        "queue": "SINGLE_CANDIDATE_REVIEW",
        "generated_from": {"assembled_regimens_sha256": ASSEMBLED_SHA, "candidate_manifest": "generated/rc030_c67/candidate_117_manifest.json"},
        "queue_size": len(queue_b_records),
        "selection_criteria": "All 43 SAFE_SINGLE_CANDIDATE, grouped by review_reason_group (Part VI of RC030_C67_SINGLE_CANDIDATE_DISPOSITION.md) -- never migration-safe regardless of any future confirmation.",
        "records": queue_b_records,
    }

    OUT_A.write_text(json.dumps(out_a, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_B.write_text(json.dumps(out_b, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_AI.parent.mkdir(parents=True, exist_ok=True)
    OUT_AI.write_text(json.dumps({"schema_version": 1, "review_origin": "AI_PRE_REVIEW", "count": len(ai_companion), "records": ai_companion}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"QUEUE A (exact-link confirmation): {len(queue_a_records)} records -> {OUT_A}")
    print(f"QUEUE B (single-candidate review): {len(queue_b_records)} records -> {OUT_B}")
    print(f"AI pre-review companion (not owner-facing): {len(ai_companion)} records -> {OUT_AI}")

    for doc in pdf_cache.values():
        doc.close()


if __name__ == "__main__":
    main()
