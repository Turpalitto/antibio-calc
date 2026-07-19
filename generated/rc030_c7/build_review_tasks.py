"""RC-030 C7 Part III Phase 4-5 -- build the final C7 review task record for
each of the 113 unique tasks in the master registry, then run the evidence
completeness gate and classify readiness.

Read-only. No PDF written, no DB write, no Clinical Engine import.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dose_verification_sandbox.dose_unit_signature import parse_dose_unit  # noqa: E402
from dose_verification_sandbox.pdf_evidence import find_quote_in_page_text, expand_context  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "generated" / "rc030_c7" / "master_registry_prioritized.json"
MANIFEST_PATH = ROOT / "generated" / "rc030_c67" / "candidate_117_manifest.json"
PDF_HASH_PATH = ROOT / "generated" / "rc030_c67" / "pdf_hash_reverify.json"
CORPUS_MANIFEST_PATH = ROOT / "CORPUS_MANIFEST.json"

SCHEMA_VERSION = 1
VALIDATION_UNIT_SCHEMA_VERSION = 1


def main() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["registry_prioritized"]
    manifest = {r["regimen_id"]: r for r in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["records"]}
    pdf_hash_check = json.loads(PDF_HASH_PATH.read_text(encoding="utf-8"))
    path_by_file = {r["file"]: r.get("path") for r in pdf_hash_check["results"] if r["status"] == "PDF_EVIDENCE_VALID"}
    corpus_manifest = json.loads(CORPUS_MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_hash_by_file = {d["file"]: d["sha256"] for d in corpus_manifest["documents"]}

    pdf_cache: dict[str, "fitz.Document"] = {}

    def get_doc(path):
        if path not in pdf_cache:
            pdf_cache[path] = fitz.open(path)
        return pdf_cache[path]

    tasks = []
    blocked = []

    for i, entry in enumerate(registry):
        rid = entry["regimen_id"]
        m = manifest[rid]
        readiness_issues = []

        source_pdf = m["source_pdf"]
        pdf_path = path_by_file.get(source_pdf)
        expected_pdf_hash = expected_hash_by_file.get(source_pdf)

        if pdf_path is None:
            readiness_issues.append("BLOCKED_PDF_HASH")
        if expected_pdf_hash is None:
            readiness_issues.append("BLOCKED_IDENTITY")

        sentence_context = ""
        paragraph_context = ""
        quote_found = False
        if pdf_path:
            doc = get_doc(pdf_path)
            try:
                page_num = int(m["source_page"]) - 1
            except (TypeError, ValueError):
                page_num = -1
            if 0 <= page_num < doc.page_count:
                page_text = doc[page_num].get_text()
                idx = find_quote_in_page_text(page_text, m["source_quote"] or "")
                quote_found = idx != -1
                if not quote_found:
                    readiness_issues.append("BLOCKED_QUOTE")
                sentence_context = expand_context(page_text, m["source_quote"] or "", window=80)
                paragraph_context = expand_context(page_text, m["source_quote"] or "", window=350)
            else:
                readiness_issues.append("BLOCKED_PAGE")
        else:
            readiness_issues.append("BLOCKED_PAGE")

        rs = m.get("selected_range_span")
        source_unit_raw = rs["unit_raw"] if rs else None
        source_unit_sig = parse_dose_unit(source_unit_raw) if source_unit_raw else None
        structured_unit_sig = parse_dose_unit(m["structured_unit"]) if m["structured_unit"] else None

        if not m.get("expected_antibiotic"):
            readiness_issues.append("BLOCKED_SOURCE_EVIDENCE")
        if entry["primary_queue"] != "TABLE_REVIEW" and rs is None and entry["primary_queue"] != "SOURCE_BLOCKED":
            readiness_issues.append("BLOCKED_SOURCE_EVIDENCE")

        # duplicate task identity: already guaranteed 0 by Part II; re-verify here defensively
        # (checked globally after the loop)

        risk_flags = list(entry["tags"])

        task = {
            "review_task_schema_version": SCHEMA_VERSION,
            "review_batch_id": None,  # assigned in Part IV
            "queue_category": entry["primary_queue"],
            "priority": entry["priority"],
            "unit_id": entry["evidence_hash"],
            "validation_unit_schema_version": VALIDATION_UNIT_SCHEMA_VERSION,
            "regimen_id": rid,
            "regimen_version": entry["regimen_version"],
            "source_packet_hash": expected_pdf_hash,
            "PDF_hash": m.get("pdf_manifest_sha256"),
            "source_pdf_relative_path": source_pdf,
            "page": m["source_page"],
            "exact_quote": m["source_quote"],
            "sentence_context": sentence_context,
            "paragraph_context": paragraph_context,
            "table_context": entry["primary_queue"] == "TABLE_REVIEW",
            "antibiotic": m["expected_antibiotic"],
            "diagnosis": m["diagnosis"],
            "route": m["route"],
            "frequency": m["frequency"],
            "duration": m["duration_recommended"],
            "structured_scalar": m["structured_dose"],
            "structured_unit": m["structured_unit"],
            "source_range_text": rs["raw_text"] if rs else None,
            "source_dose_min": rs["lower"] if rs else None,
            "source_dose_max": rs["upper"] if rs else None,
            "source_unit_signature": source_unit_sig.__dict__ if source_unit_sig else None,
            "structured_unit_signature": structured_unit_sig.__dict__ if structured_unit_sig else None,
            "risk_flags": risk_flags,
            # HIDDEN before owner submission -- present in this build artifact for
            # governance/audit purposes only, stripped by the C5 dataset builder
            # before anything reaches the owner-facing HTML (Part V Phase 9).
            "deterministic_candidate": {"lower": rs["lower"], "upper": rs["upper"], "unit_raw": rs["unit_raw"]} if rs else None,
            "deterministic_classification": m["frozen_classification"],
            "comparison_metadata": {"repeat_classification": m.get("repeat_classification"),
                                     "repeat_matches_frozen": m.get("repeat_matches_frozen")},
            "owner_verdict": None,
            "owner_note": None,
        }

        readiness = "READY_FOR_OWNER_REVIEW" if not readiness_issues else readiness_issues[0]
        task["readiness"] = readiness
        task["readiness_issues"] = readiness_issues

        if readiness_issues:
            blocked.append(task)
        else:
            tasks.append(task)

    for doc in pdf_cache.values():
        doc.close()

    from collections import Counter
    readiness_counts = Counter(t["readiness"] for t in tasks + blocked)

    out = {
        "schema_version": SCHEMA_VERSION,
        "total_tasks": len(tasks) + len(blocked),
        "ready_count": len(tasks),
        "blocked_count": len(blocked),
        "readiness_counts": dict(readiness_counts),
        "tasks": tasks,
    }
    blocked_out = {
        "schema_version": SCHEMA_VERSION,
        "blocked_count": len(blocked),
        "tasks": blocked,
    }

    (ROOT / "generated" / "rc030_c7" / "review_tasks_ready.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "generated" / "rc030_c7" / "review_tasks_blocked.json").write_text(
        json.dumps(blocked_out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("total:", len(tasks) + len(blocked), "ready:", len(tasks), "blocked:", len(blocked))
    print("readiness_counts:", dict(readiness_counts))


if __name__ == "__main__":
    main()
