"""Validate and consolidate the final RC-030 C7 owner-review exports.

This is a local, fail-closed audit utility. It never writes clinical or
production data and never grants calculation eligibility.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dose_verification_sandbox.owner_fidelity_events import validate_events  # noqa: E402


VISIBLE_DATASET_DIR = ROOT / "generated" / "rc030_c7_owner_review"
DATASET_MANIFEST = VISIBLE_DATASET_DIR / "datasets_manifest.json"
REPAIRED_DATASET = (
    VISIBLE_DATASET_DIR / "correction_07_source_repair_dataset.json"
)
AI_EVENTS = ROOT / "RC030_C7_AI_PRE_REVIEW_EVENTS.json"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def _source_export_metadata(path: Path) -> dict:
    return {
        "file_name": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
    }


def _known_records() -> list[dict]:
    manifest = _load_json(DATASET_MANIFEST)
    records: list[dict] = []
    for item in manifest["datasets"]:
        records.extend(_load_json(ROOT / item["dataset_path"].replace("\\", "/"))["records"])
    records.extend(_load_json(REPAIRED_DATASET)["records"])
    return records


def _terminal_events(events: list[dict]) -> dict[str, dict]:
    terminal: dict[str, dict] = {}
    for event in sorted(events, key=lambda item: item["created_at"]):
        terminal[str(event["regimen_id"])] = event
    return terminal


def comparison_status(owner_verdict: str, ai_verdict: str) -> str:
    if owner_verdict == ai_verdict:
        return "EXACT_MATCH"
    if (
        owner_verdict == "CORRECT_EXPLICIT_PER_DOSE"
        and ai_verdict == "CORRECT_RANGE_SINGLE"
    ):
        return "LABEL_EQUIVALENT_PER_ADMINISTRATION"
    return "SUBSTANTIVE_MISMATCH"


def consolidate(
    source_exports: list[Path],
    output_dir: Path,
) -> tuple[Path, Path]:
    events: list[dict] = []
    for path in source_exports:
        loaded = _load_json(path)
        if not isinstance(loaded, list):
            raise ValueError(f"{path}: expected a JSON event list")
        events.extend(loaded)

    issues = validate_events(events, _known_records())
    if issues:
        rendered = [
            {"index": issue.index, "field": issue.field, "message": issue.message}
            for issue in issues
        ]
        raise ValueError(
            "owner event validation failed:\n"
            + json.dumps(rendered, ensure_ascii=False, indent=2)
        )

    terminal = _terminal_events(events)
    if len(terminal) != 113:
        raise ValueError(f"expected 113 terminal regimens, got {len(terminal)}")

    ai_payload = _load_json(AI_EVENTS)
    ai_by_id = {
        str(event["regimen_id"]): event for event in ai_payload["events"]
    }
    if set(ai_by_id) != set(terminal):
        raise ValueError("owner and AI regimen identity sets do not match")

    comparison_rows = []
    for regimen_id in sorted(terminal, key=int):
        owner_verdict = terminal[regimen_id]["canonical_verdict"]
        ai_verdict = ai_by_id[regimen_id]["final_ai_verdict"]
        status = comparison_status(owner_verdict, ai_verdict)
        comparison_rows.append(
            {
                "regimen_id": regimen_id,
                "owner_terminal_verdict": owner_verdict,
                "ai_verdict": ai_verdict,
                "status": status,
            }
        )

    comparison_counts = Counter(row["status"] for row in comparison_rows)
    if comparison_counts.get("SUBSTANTIVE_MISMATCH", 0):
        raise ValueError(
            "substantive owner/AI mismatches remain: "
            + json.dumps(
                [
                    row
                    for row in comparison_rows
                    if row["status"] == "SUBSTANTIVE_MISMATCH"
                ],
                ensure_ascii=False,
            )
        )

    comparison = {
        "schema_version": 1,
        "source_exports": [
            _source_export_metadata(path) for path in source_exports
        ],
        "event_count": len(events),
        "unique_regimens": len(terminal),
        "validation_issue_count": 0,
        "terminal_verdict_counts": dict(
            Counter(event["canonical_verdict"] for event in terminal.values())
        ),
        "comparison_counts": dict(comparison_counts),
        "rows": comparison_rows,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "RC030_C7_FINAL_OWNER_EVENTS_2026-07-30.json"
    comparison_path = output_dir / "RC030_C7_FINAL_COMPARISON_2026-07-30.json"
    events_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    comparison_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return events_path, comparison_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-export",
        action="append",
        required=True,
        type=Path,
        help="Repeat exactly once for each final mode export.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    events_path, comparison_path = consolidate(
        args.source_export, args.output_dir
    )
    result = _load_json(comparison_path)
    print(
        json.dumps(
            {
                "events_path": str(events_path),
                "comparison_path": str(comparison_path),
                "event_count": result["event_count"],
                "unique_regimens": result["unique_regimens"],
                "validation_issue_count": result["validation_issue_count"],
                "comparison_counts": result["comparison_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
