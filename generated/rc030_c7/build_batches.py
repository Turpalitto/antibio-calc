"""RC-030 C7 Part IV Phase 6 -- assign the 113 ready review tasks into
deterministic batches small enough for reliable human review, following
the spec's recommended shape (12/12/rest for exact-link, then
disagreement/high-risk, then remaining unit-basis/table/single).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IN_PATH = ROOT / "generated" / "rc030_c7" / "review_tasks_ready.json"
OUT_PATH = ROOT / "generated" / "rc030_c7" / "batch_manifest.json"

BATCH_SIZE = 12


def chunk(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def complexity_for(task) -> str:
    if task["queue_category"] == "TABLE_REVIEW":
        return "HIGH"
    if task["queue_category"] in ("UNIT_BASIS_REVIEW", "ENGINE_DISAGREEMENT"):
        return "MEDIUM"
    return "LOW"


def main() -> None:
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    tasks = data["tasks"]

    by_cat = {}
    for t in tasks:
        by_cat.setdefault(t["queue_category"], []).append(t)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda t: (t["regimen_id"], t["regimen_version"]))

    batches = []
    batch_id = 1

    # Priority 1: exact-link, 12/12/12
    exact = by_cat.get("EXACT_LINK_CONFIRMATION", [])
    for group in chunk(exact, BATCH_SIZE):
        batches.append((f"batch_{batch_id:02d}_exact", group))
        batch_id += 1

    # Priority 2: engine disagreement (own batch, small and highest-risk)
    engine = by_cat.get("ENGINE_DISAGREEMENT", [])
    if engine:
        batches.append((f"batch_{batch_id:02d}_engine_disagreement", engine))
        batch_id += 1

    # Priority 2: unit-basis review, chunked
    unit_basis = by_cat.get("UNIT_BASIS_REVIEW", [])
    for group in chunk(unit_basis, BATCH_SIZE):
        batches.append((f"batch_{batch_id:02d}_unit_basis", group))
        batch_id += 1

    # Priority 3: table review (single batch, small)
    table = by_cat.get("TABLE_REVIEW", [])
    if table:
        batches.append((f"batch_{batch_id:02d}_table_review", table))
        batch_id += 1

    # Priority 4: general single-candidate + source-blocked (empty)
    single = by_cat.get("GENERAL_SINGLE_CANDIDATE", []) + by_cat.get("SOURCE_BLOCKED", [])
    for group in chunk(single, BATCH_SIZE):
        batches.append((f"batch_{batch_id:02d}_single_candidate", group))
        batch_id += 1

    manifest_batches = []
    for bid, group in batches:
        for t in group:
            t["review_batch_id"] = bid
        cat_counts = {}
        for t in group:
            cat_counts[t["queue_category"]] = cat_counts.get(t["queue_category"], 0) + 1
        complexities = {complexity_for(t) for t in group}
        overall_complexity = "HIGH" if "HIGH" in complexities else ("MEDIUM" if "MEDIUM" in complexities else "LOW")
        pdf_count = len({t["source_pdf_relative_path"] for t in group})
        manifest_batches.append({
            "batch_id": bid,
            "task_count": len(group),
            "category_counts": cat_counts,
            "pdf_count": pdf_count,
            "estimated_complexity": overall_complexity,
            "source_evidence_readiness": "READY_FOR_OWNER_REVIEW",
            "task_unit_ids": [t["unit_id"] for t in group],
        })

    total_assigned = sum(b["task_count"] for b in manifest_batches)
    manifest = {
        "schema_version": 1,
        "batch_count": len(manifest_batches),
        "total_tasks": total_assigned,
        "batches": manifest_batches,
    }
    OUT_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # write per-batch task files (compact, evidence-minimized -- see Phase 14)
    batch_dir = ROOT / "review_batches" / "c7"
    batch_dir.mkdir(parents=True, exist_ok=True)
    all_tasks_by_batch = {}
    for bid, group in batches:
        all_tasks_by_batch.setdefault(bid, []).extend(group)
    for bid, group in all_tasks_by_batch.items():
        (batch_dir / f"{bid}.json").write_text(
            json.dumps({"schema_version": 1, "batch_id": bid, "task_count": len(group), "tasks": group},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    (batch_dir / "batch_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"batches: {len(manifest_batches)}, total_tasks: {total_assigned}")
    for b in manifest_batches:
        print(" ", b["batch_id"], b["task_count"], b["category_counts"], b["estimated_complexity"])


if __name__ == "__main__":
    main()
