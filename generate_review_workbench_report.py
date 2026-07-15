"""Generate deterministic review queue inventory from an existing review artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clinical_engine.review_workbench.reporting import summarize_queue
from clinical_engine.review_workbench.storage import ReviewStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="review_workbench_p56.sqlite")
    parser.add_argument("--out", default="p56_queue_report.json")
    args = parser.parse_args()
    with ReviewStore(args.database) as store:
        report = summarize_queue(store)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "total": report["measured"]["total"],
        "projected_hours": report["workload_projection"]["projected_hours"],
    }))


if __name__ == "__main__":
    main()
