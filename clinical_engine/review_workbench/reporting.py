"""Measured queue inventory and transparent workload projection."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .storage import ReviewStore


PLANNING_MINUTES = {"HIGH": 20, "MEDIUM": 12, "LOW": 7}


def summarize_queue(store: ReviewStore) -> dict[str, Any]:
    tasks = store.list_tasks(limit=1_000_000)
    by_severity: Counter[str] = Counter()
    by_safety_axis: Counter[str] = Counter()
    by_diagnosis: Counter[str] = Counter()
    by_guideline: Counter[str] = Counter()
    projected_minutes = 0
    for task in tasks:
        by_severity[task.severity.value] += 1
        by_safety_axis.update(task.safety_axes or ("NONE",))
        projected_minutes += PLANNING_MINUTES[task.priority.value]
        snapshot = store.target_snapshot(task)
        payload = snapshot["payload"]
        diagnosis = str(
            payload.get("diagnosis") or payload.get("indication")
            or payload.get("diagnosis_id") or "UNKNOWN"
        )
        by_diagnosis[diagnosis] += 1
        guideline_ids = {
            str(source.get("guideline_id"))
            for source in snapshot["source_references"]
            if source.get("guideline_id") not in (None, "")
        }
        if not guideline_ids:
            guideline_ids = {"UNKNOWN"}
        by_guideline.update(guideline_ids)
    return {
        "measured": {
            **store.metrics(),
            "by_severity": dict(sorted(by_severity.items())),
            "by_safety_axis": dict(by_safety_axis.most_common()),
            "by_diagnosis": dict(by_diagnosis.most_common()),
            "by_guideline": dict(by_guideline.most_common()),
        },
        "workload_projection": {
            "status": "PLANNING_ESTIMATE_NOT_BENCHMARK",
            "minutes_per_priority": PLANNING_MINUTES,
            "projected_minutes": projected_minutes,
            "projected_hours": round(projected_minutes / 60, 2),
            "actual_average_review_time_seconds": store.metrics()["average_review_time_seconds"],
        },
    }
