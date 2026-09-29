"""C-4 / C-5 / H-2 / H-5 -- validation pairing, correction gating and fail-closed
progress accounting in `cmd_validate`.

These exist because `src/pipeline/main.py` was previously not importable at all
(flat imports inside a package), so the pairing bug had no test at all.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import orjson
import pytest

import src.pipeline.main as pipeline_main
from src.pipeline import main as _main_mod  # noqa: F401  (import-order guard)


# ---------------------------------------------------------------------------
# unit level: index resolution
# ---------------------------------------------------------------------------

def test_result_index_is_read_not_guessed():
    assert pipeline_main._resolve_result_index({"index": 2}, 0, 5) == (2, "")


def test_result_without_index_is_refused():
    position, problem = pipeline_main._resolve_result_index({"valid": True}, 0, 3)
    assert position is None
    assert "no 'index'" in problem


def test_result_with_non_integer_index_is_refused():
    position, problem = pipeline_main._resolve_result_index({"index": "один"}, 0, 3)
    assert position is None
    assert "non-integer" in problem


@pytest.mark.parametrize("bad_index", [-1, 5, 99])
def test_result_with_out_of_range_index_is_refused(bad_index):
    position, problem = pipeline_main._resolve_result_index({"index": bad_index}, 0, 3)
    assert position is None
    assert "out-of-range" in problem


def test_bool_index_is_refused_not_coerced_to_position_1():
    # `True` is an int subclass; treating it as index 1 would be a silent mis-pair.
    position, problem = pipeline_main._resolve_result_index({"index": True}, 0, 3)
    assert position is None
    assert "non-integer" in problem


def test_non_dict_result_is_refused():
    position, problem = pipeline_main._resolve_result_index("строка", 0, 3)
    assert position is None
    assert "not an object" in problem


# ---------------------------------------------------------------------------
# unit level: C-5 correction gating
# ---------------------------------------------------------------------------

_SECTION = {"relevant_text": "Амоксициллин 500 мг 3 раза в день", "relevant_pages": [1]}


def test_correction_with_a_plain_field_is_accepted():
    corrected, problem = pipeline_main._validated_correction(
        {"dose": "500-1000", "frequency": "3 раза в день"}, {}, _SECTION,
    )
    assert corrected == {"dose": "500-1000", "frequency": "3 раза в день"}
    assert problem == ""


def test_correction_that_rewrites_identity_is_rejected():
    corrected, problem = pipeline_main._validated_correction(
        {"pdf_sha256": "sha256:0000"}, {}, _SECTION,
    )
    assert corrected is None
    assert "pdf_sha256" in problem


def test_correction_that_rewrites_a_provenance_locator_is_rejected():
    """page_number/section_name cannot be verified against the source text."""
    for field, value in (("page_number", "999"), ("section_name", "выдумано")):
        corrected, problem = pipeline_main._validated_correction({field: value}, {}, _SECTION)
        assert corrected is None
        assert field in problem


def test_correction_with_a_supported_quote_is_accepted():
    corrected, problem = pipeline_main._validated_correction(
        {"source_quote": "Амоксициллин 500 мг 3 раза в день"}, {}, _SECTION,
    )
    assert corrected is not None
    assert problem == ""


def test_correction_that_is_not_an_object_is_rejected():
    corrected, problem = pipeline_main._validated_correction(["dose"], {}, _SECTION)
    assert corrected is None
    assert "not an object" in problem


def test_correction_with_a_container_field_is_rejected():
    corrected, problem = pipeline_main._validated_correction(
        {"dose": {"value": 500}}, {}, _SECTION,
    )
    assert corrected is None
    assert "expected a scalar" in problem


def test_empty_correction_is_a_no_op():
    for value in (None, {}, []):
        assert pipeline_main._validated_correction(value, {}, _SECTION) == (None, "")


# ---------------------------------------------------------------------------
# integration level: cmd_validate
# ---------------------------------------------------------------------------

def _regimen(n: int, quote: str = "Амоксициллин 500 мг 3 раза в день") -> dict[str, Any]:
    return {
        "clinrec_id": 2199,
        "clinrec_name": "Внебольничная пневмония",
        "code_version": "123_6",
        "pdf_file": "ВП.pdf",
        "guideline_name": "Внебольничная пневмония",
        "regimen_type": "first_line",
        "antibiotic": "амоксициллин",
        "dose": f"{n} мг",
        "page_number": str(10 + n),
        "section_name": "Антибактериальная терапия",
        "source_quote": quote,
    }


@pytest.fixture
def validate_env(tmp_path, monkeypatch):
    """Run cmd_validate against an isolated on-disk pipeline state."""
    raw = tmp_path / "extraction_raw.json"
    validated = tmp_path / "extraction_validated.json"
    review = tmp_path / "review_required.json"
    raw.write_bytes(orjson.dumps([_regimen(100), _regimen(200), _regimen(300)]))

    monkeypatch.setattr(pipeline_main, "EXTRACTION_RAW_JSON", raw)
    monkeypatch.setattr(pipeline_main, "EXTRACTION_VALIDATED_JSON", validated)
    monkeypatch.setattr(pipeline_main, "REVIEW_REQUIRED_JSON", review)
    monkeypatch.setattr(pipeline_main, "_load_items", lambda: [
        {"Id": 2199, "Name": "ВП", "abx_level": "A", "pdf_path": ""},
    ])
    monkeypatch.setattr(pipeline_main, "load_progress", lambda: {"items": {}})
    monkeypatch.setattr(pipeline_main, "detect_sections", lambda *a, **k: _SECTION)

    marked: list[tuple[int, float]] = []
    monkeypatch.setattr(
        pipeline_main, "mark_validation_done",
        lambda cid, conf: marked.append((cid, conf)),
    )

    def _run(results, section_data=None):
        async def _validate(_regimens, _section):
            return results
        monkeypatch.setattr(pipeline_main, "validate_regimens", _validate)
        import asyncio
        asyncio.run(pipeline_main.cmd_validate(argparse.Namespace()))
        out_validated = orjson.loads(validated.read_bytes()) if validated.exists() else []
        out_review = orjson.loads(review.read_bytes()) if review.exists() else []
        return out_validated, out_review, marked

    return _run


def test_c4_results_are_paired_by_index_not_position(validate_env):
    """A verdict naming index 2 must land on regimen #2, not on regimen #0."""
    results = [{
        "index": 2, "valid": True, "confidence": 0.95, "issues": [],
        "corrected": {"dose": "300 мг"},
    }]
    validated, review, _marked = validate_env(results)
    assert len(validated) == 1
    assert validated[0]["page_number"] == "310", "verdict was paired with the WRONG regimen"
    assert validated[0]["dose"] == "300 мг"
    assert validated[0]["validated"] == 1
    # the two regimens the validator did not name keep their data and go to review
    assert {item["page_number"] for item in review} == {"110", "210"}
    assert all(item["extracted_data"] for item in review), "extracted data was destroyed"


def test_c4_reordered_results_pair_correctly(validate_env):
    results = [
        {"index": 2, "valid": True, "confidence": 0.95, "issues": [], "corrected": None},
        {"index": 0, "valid": True, "confidence": 0.95, "issues": [], "corrected": None},
        {"index": 1, "valid": True, "confidence": 0.95, "issues": [], "corrected": None},
    ]
    validated, review, _marked = validate_env(results)
    assert sorted(r["page_number"] for r in validated) == ["110", "210", "310"]
    assert review == []


def test_c4_omitted_result_does_not_mispair(validate_env):
    """One verdict for three regimens: 2 accepted by index, 1 queued unpaired."""
    results = [
        {"index": 0, "valid": True, "confidence": 0.95, "issues": [], "corrected": None},
    ]
    validated, review, _marked = validate_env(results)
    assert [r["page_number"] for r in validated] == ["110"]
    assert {item["reason"] for item in review} == {"validation_result_missing"}
    assert {item["page_number"] for item in review} == {"210", "310"}
    assert all(item["extracted_data"].get("dose") for item in review)


def test_c4_missing_index_is_refused_not_guessed(validate_env):
    results = [{"valid": True, "confidence": 0.95, "issues": [], "corrected": None}]
    validated, review, _marked = validate_env(results)
    assert validated == [], "a verdict with no index must never be promoted to validated"
    reasons = {item["reason"] for item in review}
    assert "validation_result_index_invalid" in reasons
    assert "validation_result_missing" in reasons


def test_c4_out_of_range_index_is_refused(validate_env):
    results = [{"index": 99, "valid": True, "confidence": 0.95, "issues": [], "corrected": None}]
    validated, review, _marked = validate_env(results)
    assert validated == []
    assert any(item["reason"] == "validation_result_index_invalid" for item in review)


def test_c5_protected_field_rewrite_is_rejected_and_queued(validate_env):
    results = [{
        "index": 0, "valid": True, "confidence": 0.99, "issues": [],
        "corrected": {"pdf_sha256": "sha256:forged"},
    }]
    validated, review, _marked = validate_env(results)
    # regimen 0 carries the rejected correction; 1 and 2 were never mentioned.
    assert {item["reason"] for item in review} == {"validation_failed", "validation_result_missing"}
    forged = [item for item in review if item["reason"] == "validation_failed"]
    assert len(forged) == 1
    assert "protected fields" in " ".join(forged[0]["validation_issues"])
    assert forged[0]["extracted_data"].get("pdf_sha256") is None
    assert validated == [], "a rejected correction must never reach extraction_validated.json"


def test_c5_invented_source_quote_is_rejected(validate_env):
    results = [{
        "index": 0, "valid": True, "confidence": 0.99, "issues": [],
        "corrected": {"source_quote": "Амоксициллин 9999 мг"},
    }]
    validated, review, _marked = validate_env(results)
    assert "not present in the source text" in " ".join(review[0]["validation_issues"])
    assert validated == []


def test_h5_empty_results_does_not_mark_validation_done(validate_env):
    validated, review, marked = validate_env([])
    assert validated == []
    assert marked == [], "nothing was processed, so validation must NOT be marked done"
    assert {item["reason"] for item in review} == {"validation_returned_no_results"}
    assert len(review) == 3, "every regimen must be preserved for review"


def test_review_queue_is_deduped_on_write(tmp_path):
    from src.pipeline.database import save_review_required

    path = tmp_path / "review_required.json"
    item = {
        "clinrec_id": 1, "pdf_file": "a.pdf", "page_number": "5", "section_name": "s",
        "reason": "validation_failed", "extracted_data": {"dose": "500"},
    }
    save_review_required([item, dict(item)], path)
    save_review_required([item, dict(item), dict(item)], path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload) == 1


def test_review_dedup_keeps_a_changed_item(tmp_path):
    from src.pipeline.database import save_review_required

    path = tmp_path / "review_required.json"
    base = {
        "clinrec_id": 1, "pdf_file": "a.pdf", "page_number": "5", "section_name": "s",
        "reason": "validation_failed", "extracted_data": {"dose": "500"},
    }
    updated = {**base, "extracted_data": {"dose": "750"}}
    save_review_required([base], path)
    save_review_required([base, updated], path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload) == 1, "same (clinrec, page, section, reason) is ONE review request"
    assert payload[0]["extracted_data"] == {"dose": "750"}, "the newer payload must win"


def test_safe_write_is_atomic_and_never_truncates(tmp_path):
    """H-4: a crash mid-write must not leave a truncated authoritative file."""
    import asyncio

    target = tmp_path / "extraction_raw.json"
    original = [{"clinrec_id": i} for i in range(50)]
    asyncio.run(pipeline_main._safe_write(target, original))
    assert orjson.loads(target.read_bytes()) == original
    # no staging files left behind
    assert [p.name for p in tmp_path.iterdir()] == ["extraction_raw.json"]


def test_safe_write_rejects_non_list_payload_without_touching_the_file(tmp_path):
    import asyncio

    target = tmp_path / "extraction_raw.json"
    target.write_bytes(orjson.dumps([{"keep": True}]))
    with pytest.raises(RuntimeError):
        asyncio.run(pipeline_main._safe_write(target, {"not": "a list"}))
    assert orjson.loads(target.read_bytes()) == [{"keep": True}], "target was damaged"
    assert [p.name for p in tmp_path.iterdir()] == ["extraction_raw.json"]


# ---------------------------------------------------------------------------
# H-3 -- a fail-open extraction outcome must stay retryable
# ---------------------------------------------------------------------------

def test_mark_extraction_incomplete_keeps_the_item_pending(tmp_path, monkeypatch):
    from src.pipeline import progress as progress_mod

    path = tmp_path / "extraction_progress.json"
    monkeypatch.setattr(progress_mod, "EXTRACTION_PROGRESS_JSON", path)

    progress_mod.mark_extraction_incomplete(7, "sha256:abc", "no_relevant_text")
    data = progress_mod.load_progress()
    entry = data["items"]["7"]
    assert entry["extraction_done"] is False
    assert entry["extraction_incomplete"] is True
    assert entry["extraction_incomplete_reason"] == "no_relevant_text"
    # the item must still be offered for retry
    assert {"Id": 7} and progress_mod.get_pending_items([{"Id": 7}]) == [{"Id": 7}]
    assert progress_mod.needs_reprocessing(7, "sha256:abc") is True


def test_mark_extraction_incomplete_never_clears_a_validation_flag(tmp_path, monkeypatch):
    from src.pipeline import progress as progress_mod

    path = tmp_path / "extraction_progress.json"
    monkeypatch.setattr(progress_mod, "EXTRACTION_PROGRESS_JSON", path)
    progress_mod.mark_extraction_done(7, "sha256:abc", 5)
    progress_mod.mark_extraction_incomplete(7, "sha256:abc", "zero_regimens")
    entry = progress_mod.load_progress()["items"]["7"]
    assert entry["extraction_done"] is False
    assert entry["extraction_incomplete"] is True


def test_progress_write_is_atomic(tmp_path, monkeypatch):
    from src.pipeline import progress as progress_mod

    path = tmp_path / "extraction_progress.json"
    monkeypatch.setattr(progress_mod, "EXTRACTION_PROGRESS_JSON", path)
    progress_mod.mark_extraction_done(1, "sha256:a", 1)
    assert [p.name for p in tmp_path.iterdir()] == ["extraction_progress.json"]
