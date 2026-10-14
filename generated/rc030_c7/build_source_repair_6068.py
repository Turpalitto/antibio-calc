"""Build the governed, owner-facing source repair for regimen 6068.

The source PDF is immutable. This script creates a derived validation unit
whose quote preserves the visually verified superscript footnote markers
instead of treating them as dose digits. The changed evidence receives a
new identity hash and remains blocked from calculation/clinical approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "generated" / "rc030_c7_owner_review"
OUTPUT_DATASET = SOURCE_DIR / "correction_07_source_repair_dataset.json"

REGIMEN_ID = "6068"
EXPECTED_ORIGINAL_RANGE = "5001- 10002 мг"
REPAIRED_QUOTE = (
    "Амоксициллин** (Код АТХ: J01CA04) внутрь "
    "500¹-1000² мг 3 раза в сутки взрослым 5-10 дней"
)


def _compute_evidence_hash(record: dict) -> str:
    payload = json.dumps(
        {
            "regimen_id": record["regimen_id"],
            "regimen_version": record["regimen_version"],
            "source_pdf": record["source_pdf"],
            "source_page": record["source_page"],
            "source_quote": record["source_quote"],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_original() -> dict:
    manifest = json.loads(
        (SOURCE_DIR / "datasets_manifest.json").read_text(encoding="utf-8")
    )
    matches: list[dict] = []
    for item in manifest["datasets"]:
        dataset = json.loads(
            (ROOT / item["dataset_path"].replace("\\", "/")).read_text(encoding="utf-8")
        )
        matches.extend(
            record
            for record in dataset["records"]
            if str(record["regimen_id"]) == REGIMEN_ID
        )
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one original record {REGIMEN_ID}, got {len(matches)}"
        )
    return matches[0]


def build() -> dict:
    original = _load_original()
    if original.get("source_range_text") != EXPECTED_ORIGINAL_RANGE:
        raise ValueError(
            "6068 original extraction no longer matches the governed repair "
            f"precondition: {original.get('source_range_text')!r}"
        )

    repaired = {
        **original,
        "source_quote": REPAIRED_QUOTE,
        "source_range_text": "500-1000 мг",
        "source_dose_min": 500.0,
        "source_dose_max": 1000.0,
        "correction_required": True,
        "correction_round": "correction_07_source_repair",
        "correction_instruction": (
            "PDF показывает 500¹-1000² мг. Надстрочные ¹ и ² — номера "
            "сносок, поэтому проверяемый диапазон дозы равен 500-1000 мг "
            "за один приём; частота указана отдельно: 3 раза в сутки."
        ),
        "source_repair": {
            "repair_type": "FLATTENED_SUPERSCRIPT_FOOTNOTE_MARKERS",
            "original_extracted_range": EXPECTED_ORIGINAL_RANGE,
            "visual_pdf_range": "500¹-1000² мг",
            "normalized_numeric_range": "500-1000 мг",
            "pdf_page": 16,
            "verification_method": "VISUAL_PDF_RENDER",
            "source_pdf_modified": False,
            "production_database_modified": False,
        },
        "calculation_eligibility": "BLOCKED",
        "clinically_approved": False,
        "authoritative_migration_allowed": False,
    }
    repaired["risk_flags"] = sorted(
        set(repaired.get("risk_flags", []))
        | {"SOURCE_EXTRACTION_REPAIRED_VISUAL_PDF"}
    )
    repaired["evidence_hash"] = _compute_evidence_hash(repaired)
    repaired["unit_id"] = repaired["evidence_hash"]
    repaired["source_packet_hash"] = repaired["evidence_hash"]

    if repaired["evidence_hash"] == original["evidence_hash"]:
        raise AssertionError("materially repaired evidence must receive a new identity")
    for forbidden in (
        "canonical_verdict",
        "owner_verdict",
        "ui_action",
        "ai_proposed_verdict",
    ):
        if forbidden in repaired:
            raise ValueError(f"forbidden preloaded field: {forbidden}")

    output = {
        "schema_version": 1,
        "generated_from": (
            "generated/rc030_c7_owner_review/*_dataset.json + "
            "visual verification of Острый ларингит.pdf page 16"
        ),
        "batch_id": "correction_07_source_repair",
        "correction_only": True,
        "records": [repaired],
    }
    OUTPUT_DATASET.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output


if __name__ == "__main__":
    result = build()
    print(
        json.dumps(
            {
                "dataset": str(OUTPUT_DATASET.relative_to(ROOT)).replace("\\", "/"),
                "regimen_id": REGIMEN_ID,
                "evidence_hash": result["records"][0]["evidence_hash"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
