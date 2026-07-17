"""RC-030 C6.8 Part VIII -- rebuild the exact-link queue plus the four
non-exact review queues (single-candidate, unit-basis-review,
table-required, engine-review-required) from the final C6.8 reconciled
117-candidate pool. Source-defect queue is intentionally empty (both
known defects, 5688/6052, were fixed in Part IV -- documented, not
silently omitted).

No verdict preloaded. No AI conclusion embedded. No owner data read or
written. Evidence fields sourced from the existing C6.7 manifest
(candidate_117_manifest.json) plus fresh context extraction, matching
the schema used by RC030_C67_EXACT_LINK_OWNER_QUEUE.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "generated" / "rc030_c67" / "candidate_117_manifest.json"
BUCKETS_PATH = ROOT / "generated" / "rc030_c68" / "final_117_buckets.json"
REPLAY_PATH = ROOT / "generated" / "rc030_c68" / "replay_365_results.json"

FORBIDDEN_KEYS = {"owner_verdict", "canonical_verdict", "ui_action", "human_fidelity_verdict"}
ASSEMBLED_SHA = "9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9"


def compute_evidence_hash(rec: dict) -> str:
    payload = json.dumps(
        {"regimen_id": rec["regimen_id"], "regimen_version": rec["regimen_version"],
         "source_pdf": rec["source_pdf"], "source_page": rec["source_page"],
         "source_quote": rec["source_quote"]},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def base_record(r: dict) -> dict:
    rec = {
        "regimen_id": r["regimen_id"],
        "regimen_version": r["regimen_version"],
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
    rec["evidence_hash"] = compute_evidence_hash(rec)
    assert not (FORBIDDEN_KEYS & rec.keys())
    return rec


def main() -> None:
    manifest = {r["regimen_id"]: r for r in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["records"]}
    buckets = json.loads(BUCKETS_PATH.read_text(encoding="utf-8"))
    replay = {r["regimen_id"]: r for r in json.loads(REPLAY_PATH.read_text(encoding="utf-8"))["all_results"]}

    reasons = {
        "5475": "Pass A: EXACT_LINK_DOWNGRADED_AMBIGUOUS", "5478": "Pass A: EXACT_LINK_DOWNGRADED_AMBIGUOUS",
        "5546": "Pass A: EXACT_LINK_DOWNGRADED_AMBIGUOUS", "5547": "Pass A: EXACT_LINK_DOWNGRADED_AMBIGUOUS",
        "5842": "Pass A: EXACT_LINK_DOWNGRADED_AMBIGUOUS", "5847": "Pass A: EXACT_LINK_DOWNGRADED_AMBIGUOUS",
        "6074": "Pass A: EXACT_LINK_DOWNGRADED_AMBIGUOUS", "6133": "Pass A: EXACT_LINK_REJECTED_WRONG_ANCHOR",
        "5683": "Pass A: EXACT_LINK_DOWNGRADED_TABLE_REQUIRED", "7258": "Pass A: EXACT_LINK_DOWNGRADED_TABLE_REQUIRED",
        "7895": "Pass A: EXACT_LINK_DOWNGRADED_TABLE_REQUIRED",
    }

    def build_queue(ids, queue_name, selection_criteria, extra_field=None):
        records = []
        for rid in sorted(ids):
            r = manifest[rid]
            rec = base_record(r)
            if extra_field:
                rec.update(extra_field(rid))
            records.append(rec)
        return {
            "schema_version": 1,
            "queue": queue_name,
            "generated_from": {"assembled_regimens_sha256": ASSEMBLED_SHA,
                                "candidate_manifest": "generated/rc030_c67/candidate_117_manifest.json",
                                "c68_reconciliation": "generated/rc030_c68/final_117_buckets.json"},
            "queue_size": len(records),
            "selection_criteria": selection_criteria,
            "records": records,
        }

    exact_q = build_queue(
        buckets["EXACT_FINAL"], "EXACT_LINK_CONFIRMATION_C68",
        "Records surviving BOTH C6.7's independent blinded Pass A audit AND C6.8's deterministic "
        "dose-basis repair -- the final, doubly-verified exact-link pool. No preselected verdict.",
    )
    single_q = build_queue(
        buckets["SINGLE_CANDIDATE"], "SINGLE_CANDIDATE",
        "SAFE_SINGLE_CANDIDATE under the C6.8-repaired engine, not otherwise routed to a specialized queue. "
        "Never migration-safe regardless of any future confirmation.",
    )
    unit_basis_q = build_queue(
        buckets["UNIT_BASIS_REVIEW"], "UNIT_BASIS_REVIEW",
        "Classification hinges on COMPATIBLE_BASIS_UNSPECIFIED -- the source text and the structured field "
        "state different (or absent) dose bases that are not in conflict but are not proven identical either. "
        "Requires a reviewer to read the source and determine the true basis.",
        extra_field=lambda rid: {"unit_compatibility": replay[rid]["unit_compatibility"]},
    )
    table_q = build_queue(
        buckets["TABLE_REQUIRED"], "TABLE_REQUIRED",
        "Source text is table-derived (flattened table row) -- requires table-layout reconstruction tooling "
        "not available in this environment before any confirming verdict is possible.",
    )
    engine_review_q = build_queue(
        buckets["ENGINE_REVIEW_REQUIRED"], "ENGINE_REVIEW_REQUIRED",
        "The C6.8-repaired engine classifies these SAFE_EXACT_LINK, but C6.7's independent blinded Pass A "
        "audit separately flagged a structural concern unrelated to dose basis (competing ranges, table shape, "
        "or wrong-anchor risk) -- both signals must be reconciled by a reviewer before either the engine's or "
        "the independent audit's conclusion is trusted.",
        extra_field=lambda rid: {"pass_a_disagreement_reason": reasons.get(rid, "unknown")},
    )
    source_defect_q = {
        "schema_version": 1, "queue": "SOURCE_QUOTE_DEFECT", "queue_size": 0,
        "selection_criteria": "Empty by construction -- both known source-quote defects (regimen_id 5688, "
        "6052) were root-caused and fixed in C6.8 Part IV (a quote-matching hyphen-linewrap bug, not a real "
        "data defect) and no longer require this queue. See RC030_C68_SOURCE_QUOTE_DEFECT_REPORT.md.",
        "records": [],
    }

    outputs = {
        "RC030_C68_EXACT_LINK_OWNER_QUEUE.json": exact_q,
        "RC030_C68_SINGLE_CANDIDATE_QUEUE.json": single_q,
        "RC030_C68_UNIT_BASIS_QUEUE.json": unit_basis_q,
        "RC030_C68_TABLE_REVIEW_QUEUE.json": table_q,
        "RC030_C68_ENGINE_REVIEW_QUEUE.json": engine_review_q,
        "RC030_C68_SOURCE_DEFECT_QUEUE.json": source_defect_q,
    }
    for fname, payload in outputs.items():
        (ROOT / fname).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{fname}: {payload['queue_size']} records")


if __name__ == "__main__":
    main()
