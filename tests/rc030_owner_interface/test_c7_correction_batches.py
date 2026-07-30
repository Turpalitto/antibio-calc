import hashlib
import json
from pathlib import Path

from generated.rc030_c7.build_correction_batches import CORRECTION_BATCHES, build
from generated.rc030_c7.build_source_repair_6068 import (
    EXPECTED_ORIGINAL_RANGE,
    REPAIRED_QUOTE,
    build as build_6068_repair,
)
from generated.rc030_c7.finalize_owner_review import comparison_status
from generated.rc030_c7.finalize_owner_review import _source_export_metadata


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "generated" / "rc030_c7_owner_review"


def test_correction_batches_cover_only_remaining_substantive_disagreements():
    expected = {
        "6296",
        "6550",
        "5475",
        "5478",
        "5441",
        "5528",
        "5824",
    }
    actual = {rid for _, _, ids in CORRECTION_BATCHES for rid in ids}
    assert actual == expected
    assert "6068" not in actual


def test_correction_datasets_keep_original_modes_and_no_preloaded_verdicts():
    written = build()
    assert [item["record_count"] for item in written] == [2, 2, 1, 2, 1, 1]
    assert [item["mode"] for item in written] == [
        "range-exact-review",
        "range-engine-review",
        "range-unit-basis-review",
        "range-single-review",
        "range-single-review",
        "range-single-review",
    ]
    for item in written:
        data = json.loads((ROOT / item["dataset"]).read_text(encoding="utf-8"))
        assert data["correction_only"] is True
        for record in data["records"]:
            assert record["correction_required"] is True
            assert record["correction_round"] == item["batch_id"]
            assert "canonical_verdict" not in record
            assert "owner_verdict" not in record
            assert "ui_action" not in record
            assert "ai_proposed_verdict" not in record


def test_owner_template_tracks_correction_progress_separately():
    source = (
        ROOT / "generated" / "rc030_recovery" / "owner_review_template.html"
    ).read_text(encoding="utf-8")
    assert "rc030_owner_review_c7_correction_progress_v1_${RECORDS[0]?.correction_round" in source
    assert "RECORDS.every(record => record.correction_required === true)" in source
    assert "if (IS_CORRECTION_BATCH) return new Set(loadCorrectionProgress());" in source
    assert "markCorrectionReviewed(r.regimen_id);" in source
    assert 'id="correctionInstruction"' in source
    retry = json.loads(
        (OUT / "correction_06_wrong_anchor_retry_dataset.json").read_text(
            encoding="utf-8"
        )
    )
    assert "15-20 мг/кг указано после этамбутола" in retry["records"][0][
        "correction_instruction"
    ]


def test_6068_source_repair_creates_new_blocked_evidence_identity():
    source = json.loads(
        (OUT / "batch_10_single_candidate_dataset.json").read_text(
            encoding="utf-8"
        )
    )
    original = next(
        record for record in source["records"] if record["regimen_id"] == "6068"
    )
    result = build_6068_repair()
    repaired = result["records"][0]

    assert original["source_range_text"] == EXPECTED_ORIGINAL_RANGE
    assert repaired["source_quote"] == REPAIRED_QUOTE
    assert repaired["source_range_text"] == "500-1000 мг"
    assert (repaired["source_dose_min"], repaired["source_dose_max"]) == (
        500.0,
        1000.0,
    )
    assert repaired["frequency"] == 3.0
    assert repaired["evidence_hash"] != original["evidence_hash"]
    assert repaired["unit_id"] == repaired["evidence_hash"]
    assert repaired["source_packet_hash"] == repaired["evidence_hash"]
    assert repaired["calculation_eligibility"] == "BLOCKED"
    assert repaired["clinically_approved"] is False
    assert repaired["authoritative_migration_allowed"] is False
    assert repaired["source_repair"]["source_pdf_modified"] is False
    assert repaired["source_repair"]["production_database_modified"] is False
    assert "canonical_verdict" not in repaired
    assert "owner_verdict" not in repaired


def test_final_comparison_closes_repaired_6068_as_exact_match():
    assert (
        comparison_status("CORRECT_RANGE_SINGLE", "CORRECT_RANGE_SINGLE")
        == "EXACT_MATCH"
    )
    assert (
        comparison_status(
            "CORRECT_EXPLICIT_PER_DOSE", "CORRECT_RANGE_SINGLE"
        )
        == "LABEL_EQUIVALENT_PER_ADMINISTRATION"
    )
    assert (
        comparison_status("WRONG_FREQUENCY_LINK", "CORRECT_RANGE_SINGLE")
        == "SUBSTANTIVE_MISMATCH"
    )


def test_finalizer_records_portable_source_export_identity(tmp_path):
    export = tmp_path / "owner-export.json"
    export.write_text("[]\n", encoding="utf-8")

    metadata = _source_export_metadata(export)

    assert metadata == {
        "file_name": "owner-export.json",
        "sha256": hashlib.sha256(export.read_bytes()).hexdigest().upper(),
    }
    assert str(tmp_path) not in str(metadata)
