"""Real local benchmark for review queue and packet lookup."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from clinical_engine.review_workbench.service import ReviewService
from clinical_engine.review_workbench.storage import ReviewStore


def _measure(operation, iterations: int) -> dict[str, float]:
    samples = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    return {
        "iterations": iterations,
        "min_ms": round(ordered[0], 3),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
        "max_ms": round(ordered[-1], 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="review_workbench_p56.sqlite")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--out", default="p56_review_benchmark.json")
    args = parser.parse_args()
    path = Path(args.database)
    with ReviewStore(path) as store:
        service = ReviewService(store)
        task_id = service.list_queue(limit=1)[0].task_id
        report = {
            "database": str(path.resolve()),
            "database_size_bytes": path.stat().st_size,
            "queue_first_page": _measure(lambda: service.list_queue(limit=100), args.iterations),
            "task_packet": _measure(lambda: service.packet(task_id), args.iterations),
            "metrics_summary": _measure(service.metrics, max(3, args.iterations // 20)),
        }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
