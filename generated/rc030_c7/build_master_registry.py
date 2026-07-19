"""RC-030 C7 Part II Phase 1-2 -- inventory all 6 C6.8 owner-review queues,
build one deterministic master registry keyed by (regimen_id,
regimen_version) (no separate validation_unit_id scheme exists upstream
of this program -- the C4/C5 schema's `evidence_hash` already encodes
regimen_id/version/source_pdf/page/quote, so it is used as the
authoritative per-record identity), deduplicate, and apply every
applicable tag (a record can carry more than one tag; this never creates
two owner tasks for the same identity).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

QUEUE_FILES = {
    "EXACT_LINK_CONFIRMATION": "RC030_C68_EXACT_LINK_OWNER_QUEUE.json",
    "GENERAL_SINGLE_CANDIDATE": "RC030_C68_SINGLE_CANDIDATE_QUEUE.json",
    "UNIT_BASIS_REVIEW": "RC030_C68_UNIT_BASIS_QUEUE.json",
    "SOURCE_BLOCKED": "RC030_C68_SOURCE_DEFECT_QUEUE.json",
    "TABLE_REVIEW": "RC030_C68_TABLE_REVIEW_QUEUE.json",
    "ENGINE_DISAGREEMENT": "RC030_C68_ENGINE_REVIEW_QUEUE.json",
}

# Supplemental tags from the finer-grained C6.7 single-candidate disposition
# (a record's C6.8 queue category is coarser than C6.7's per-reason bucket;
# these are ADDITIONAL tags on the same task identity, never a new task).
C67_SINGLE_DISPOSITION_PATH = ROOT / "generated" / "rc030_c67" / "single_candidate_disposition.json"
SUPPLEMENTAL_TAG_MAP = {
    "SINGLE_REQUIRES_PHASE_SPLIT": "PHASE_REVIEW",
    "SINGLE_REQUIRES_ALTERNATIVE_REVIEW": "ALTERNATIVE_REVIEW",
    "SINGLE_WRONG_ANCHOR": "MAXIMUM_CONFLICT",  # 5526/5533: range belongs to a different drug's per-kg maximum-adjacent figure
}


def main() -> None:
    all_records: dict[tuple[str, int], dict] = {}
    raw_total = 0
    duplicate_groups = []

    for tag, fname in QUEUE_FILES.items():
        data = json.loads((ROOT / fname).read_text(encoding="utf-8"))
        raw_total += data["queue_size"]
        for rec in data["records"]:
            key = (rec["regimen_id"], rec["regimen_version"])
            if key in all_records:
                duplicate_groups.append({"key": list(key), "queues": [all_records[key]["primary_queue"], tag],
                                          "reason": "same (regimen_id, regimen_version) appears in two C6.8 queues"})
                all_records[key]["tags"].append(tag)
            else:
                all_records[key] = {
                    "regimen_id": rec["regimen_id"],
                    "regimen_version": rec["regimen_version"],
                    "evidence_hash": rec["evidence_hash"],
                    "primary_queue": tag,
                    "tags": [tag],
                    "record": rec,
                }

    supplemental_source = {}
    supplemental_not_applicable = {}
    if C67_SINGLE_DISPOSITION_PATH.is_file():
        c67_disp = json.loads(C67_SINGLE_DISPOSITION_PATH.read_text(encoding="utf-8"))
        for rid, disp in c67_disp.items():
            extra_tag = SUPPLEMENTAL_TAG_MAP.get(disp)
            if not extra_tag:
                continue
            landed = False
            for key, entry in all_records.items():
                if key[0] == rid and extra_tag not in entry["tags"]:
                    entry["tags"].append(extra_tag)
                    landed = True
            if landed:
                supplemental_source[rid] = (disp, extra_tag)
            else:
                supplemental_not_applicable[rid] = (disp, extra_tag, "record no longer in any C6.8 queue -- rejected by the C6.8 basis repair")

    registry = []
    for key in sorted(all_records.keys(), key=lambda k: (k[0], k[1])):
        entry = all_records[key]
        registry.append({
            "regimen_id": entry["regimen_id"],
            "regimen_version": entry["regimen_version"],
            "evidence_hash": entry["evidence_hash"],
            "primary_queue": entry["primary_queue"],
            "tags": entry["tags"],
        })

    out = {
        "schema_version": 1,
        "raw_queue_total": raw_total,
        "unique_validation_units": len(registry),
        "duplicate_appearances": len(duplicate_groups),
        "duplicate_groups": duplicate_groups,
        "supplemental_tags_applied": {rid: {"c67_disposition": d, "tag": t} for rid, (d, t) in supplemental_source.items()},
        "supplemental_tags_not_applicable": {rid: {"c67_disposition": d, "tag": t, "reason": r} for rid, (d, t, r) in supplemental_not_applicable.items()},
        "final_unique_task_count": len(registry),
        "registry": registry,
    }
    out_path = ROOT / "generated" / "rc030_c7" / "master_registry.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("raw_queue_total:", raw_total)
    print("unique_validation_units:", len(registry))
    print("duplicate_appearances:", len(duplicate_groups))
    print("supplemental tags applied:", len(supplemental_source), supplemental_source)
    print("final_unique_task_count:", len(registry))


if __name__ == "__main__":
    main()
