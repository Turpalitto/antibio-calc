"""Regenerate the physician-review pilot batch using the FIXED canonical ReviewService.packet()
(RC-027 resolved) and the formalized PHYSICIAN_PILOT_V1 policy (P5.6 RC-027 Phase 8).

STRICT MODE, read-only against the queue:
- No task claimed, transitioned, or decided. No clinical value modified.
- No export-time source-text patch (RC-027 fixed in service.py; nothing to work around).
- Uses clinical_engine.review_workbench.pilot_policy (named, versioned policy module) instead of
  ad hoc ranking logic duplicated in the script.
"""
from __future__ import annotations

import json
from pathlib import Path

from clinical_engine.review_workbench.storage import ReviewStore
from clinical_engine.review_workbench.service import ReviewService
from clinical_engine.review_workbench.models import ReviewState, TargetType
from clinical_engine.review_workbench.pilot_policy import (
    POLICY_NAME, POLICY_VERSION, primary_rank, select_quota_capped,
)

DB_PATH = "review_workbench_p56.sqlite"
OUT_DIR = Path("pilot_review_batch_v2")


def select_batch(store: ReviewStore, target_type: TargetType, count: int) -> list:
    tasks = store.list_tasks(target_type=target_type, state=ReviewState.PENDING, limit=1_000_000)
    scored = [(primary_rank(t, store.target_snapshot(t)["payload"]), t) for t in tasks]
    return select_quota_capped(scored, count)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    store = ReviewStore(DB_PATH)
    service = ReviewService(store)

    regimens = select_batch(store, TargetType.CLINICAL_REGIMEN, 20)
    options = select_batch(store, TargetType.THERAPEUTIC_OPTION, 10)

    manifest = {
        "policy_name": POLICY_NAME, "policy_version": POLICY_VERSION,
        "clinical_regimen_batch": [], "therapeutic_option_batch": [],
    }

    for label, batch, key in (("ClinicalRegimen", regimens, "clinical_regimen_batch"),
                             ("TherapeuticOption", options, "therapeutic_option_batch")):
        for task in batch:
            payload = store.target_snapshot(task)["payload"]
            rank, reason, origin, _, _ = primary_rank(task, payload)
            packet_path = OUT_DIR / f"{task.task_id}.json"
            service.export_packet(task.task_id, packet_path)  # canonical path only, no patch

            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            manifest[key].append({
                "task_id": task.task_id, "target_id": task.target_id,
                "policy_rank": rank, "policy_reason": reason, "signal_origin": origin,
                "system_priority_score": task.priority_score, "system_priority_band": task.priority.value,
                "safety_axes_stored": list(task.safety_axes), "issue_type": task.issue_type,
                "source_wording_status": packet["source_wording_status"],
                "review_blocked": packet["review_blocked"],
                "packet_file": str(packet_path),
            })

    (OUT_DIR / "PILOT_REVIEW_BATCH_V2_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ClinicalRegimen selected: {len(regimens)}")
    print(f"TherapeuticOption selected: {len(options)}")
    for label, batch in (("ClinicalRegimen", regimens), ("TherapeuticOption", options)):
        from collections import Counter
        c = Counter(primary_rank(t, store.target_snapshot(t)["payload"])[1] for t in batch)
        origins = Counter(primary_rank(t, store.target_snapshot(t)["payload"])[2] for t in batch)
        blocked = sum(1 for t in batch if service.packet(t.task_id)["review_blocked"])
        print(f"{label} rank distribution:", dict(c))
        print(f"{label} signal origin:", dict(origins))
        print(f"{label} review_blocked count:", blocked)
    store.close()


if __name__ == "__main__":
    main()
