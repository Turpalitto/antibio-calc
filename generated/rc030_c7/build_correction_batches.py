"""Build correction-only C7 owner-review datasets.

The four outputs deliberately retain each record's original review mode so
the existing browser-local event store can append a genuine superseding
owner event. No verdict or AI proposal is embedded in the datasets.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "generated" / "rc030_c7_owner_review"
OUTPUT_DIR = SOURCE_DIR

CORRECTION_BATCHES = (
    ("correction_01_exact", "range-exact-review", ("6296", "6550")),
    ("correction_02_engine", "range-engine-review", ("5475", "5478")),
    (
        "correction_03_unit_basis",
        "range-unit-basis-review",
        ("5441",),
    ),
    ("correction_04_single", "range-single-review", ("5528", "5824")),
    ("correction_05_wrong_anchor", "range-single-review", ("5528",)),
    ("correction_06_wrong_anchor_retry", "range-single-review", ("5528",)),
)


def _load_visible_records() -> dict[str, dict]:
    manifest = json.loads(
        (SOURCE_DIR / "datasets_manifest.json").read_text(encoding="utf-8")
    )
    records: dict[str, dict] = {}
    for item in manifest["datasets"]:
        dataset_path = ROOT / item["dataset_path"]
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        for record in dataset["records"]:
            regimen_id = str(record["regimen_id"])
            if regimen_id in records:
                raise ValueError(f"duplicate regimen_id in visible datasets: {regimen_id}")
            records[regimen_id] = record
    return records


def build() -> list[dict]:
    source_records = _load_visible_records()
    written: list[dict] = []
    for batch_id, mode, regimen_ids in CORRECTION_BATCHES:
        missing = [rid for rid in regimen_ids if rid not in source_records]
        if missing:
            raise ValueError(f"{batch_id}: missing regimen IDs {missing}")
        records = [
            {
                **source_records[rid],
                "correction_required": True,
                "correction_round": batch_id,
            }
            for rid in regimen_ids
        ]
        if batch_id == "correction_06_wrong_anchor_retry":
            records[0]["correction_instruction"] = (
                "Сравните препараты в цитате: 15-20 мг/кг указано после "
                "этамбутола, а рифабутин имеет отдельную дозу 5 мг/кг. "
                "Если проверяемый диапазон 15-20 мг/кг не относится к "
                "рифабутину, выберите кнопку 4."
            )
        for record in records:
            for forbidden in (
                "canonical_verdict",
                "owner_verdict",
                "ui_action",
                "ai_proposed_verdict",
            ):
                if forbidden in record:
                    raise ValueError(
                        f"{batch_id}: forbidden preloaded field {forbidden!r}"
                    )
        output = OUTPUT_DIR / f"{batch_id}_dataset.json"
        output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_from": "generated/rc030_c7_owner_review/*_dataset.json",
                    "batch_id": batch_id,
                    "correction_only": True,
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(
            {
                "batch_id": batch_id,
                "mode": mode,
                "record_count": len(records),
                "dataset": str(output.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    return written


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
