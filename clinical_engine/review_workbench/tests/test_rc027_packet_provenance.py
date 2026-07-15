"""RC-027 regression tests — REVIEW_PACKET_CONTRACT.md precedence, fail-closed missing state.

Design authority: RC027_ROOT_CAUSE_REPORT.md, REVIEW_PACKET_CONTRACT.md.
"""
import os

import pytest

from clinical_engine.review_workbench.service import (
    ReviewService, resolve_source_wording, source_wording_missing,
)
from clinical_engine.review_workbench.storage import ReviewStore
from clinical_engine.review_workbench.models import TargetType, ReviewState

DB_PATH = "review_workbench_p56.sqlite"


# 1. ClinicalRegimen source_quote reaches packet.
def test_target_level_source_quote_reaches_resolver():
    provenance = [{"field": "antibiotic", "source_object_id": "x", "source_document": "d.pdf",
                  "source_location": "p1", "source_store": "kb_p44", "scope": "regimen"}]
    payload = {"source_quote": "Тедизолид 200 мг в сутки."}
    wording = resolve_source_wording(provenance, payload)
    assert wording == ["Тедизолид 200 мг в сутки."]


# 2. Field-level original_text takes precedence when present.
def test_field_level_original_text_takes_precedence():
    provenance = [{"original_text": "FIELD LEVEL QUOTE", "field": "dose"}]
    payload = {"source_quote": "TARGET LEVEL QUOTE (should not be used)"}
    wording = resolve_source_wording(provenance, payload)
    assert wording == ["FIELD LEVEL QUOTE"]


def test_field_level_source_quote_beats_target_level():
    provenance = [{"source_quote": "FIELD LEVEL SOURCE_QUOTE"}]
    payload = {"source_quote": "TARGET LEVEL (should not be used)"}
    wording = resolve_source_wording(provenance, payload)
    assert wording == ["FIELD LEVEL SOURCE_QUOTE"]


def test_golden_case_source_field_used_as_tier_4():
    provenance = [{"author": "x", "verified_at": "y", "source": "GOLDEN CASE SOURCE"}]
    payload = {}  # GoldenCase payload has no target-level source_quote
    wording = resolve_source_wording(provenance, payload)
    assert wording == ["GOLDEN CASE SOURCE"]


# 3. Multiple provenance excerpts are preserved.
def test_multiple_provenance_entries_preserved_in_order():
    provenance = [
        {"original_text": "first excerpt"},
        {"source_quote": "second excerpt"},
        {"field": "no_wording_here"},  # falls to tier 3 (target-level) if present
    ]
    payload = {"source_quote": "target level fallback"}
    wording = resolve_source_wording(provenance, payload)
    assert wording == ["first excerpt", "second excerpt", "target level fallback"]


# 4. Table row/column provenance remains attached (field_level_provenance passthrough, unchanged).
def test_table_row_col_provenance_untouched_by_fix():
    provenance = [{"field": "dose", "table_row": 3, "table_col": 1, "source_quote": "200 mg"}]
    payload = {"source_quote": "unused"}
    wording = resolve_source_wording(provenance, payload)
    assert wording == ["200 mg"]
    # the raw provenance dict itself (including table_row/table_col) is a passthrough in packet();
    # this resolver never strips or mutates the original entries.
    assert provenance[0]["table_row"] == 3 and provenance[0]["table_col"] == 1


# 5. Missing original wording blocks review.
def test_missing_wording_sets_review_blocked():
    provenance = [{"field": "x", "source_object_id": "a", "source_document": "b",
                  "source_location": "c", "source_store": "d", "scope": "regimen"}]
    payload = {}  # no target-level source_quote either -> genuinely nothing recoverable
    wording = resolve_source_wording(provenance, payload)
    assert wording == [None]
    assert source_wording_missing(wording) is True


def test_empty_provenance_list_with_no_target_quote_is_missing():
    assert resolve_source_wording([], {}) == [None]
    assert source_wording_missing([None]) is True


# 6. Empty strings do not count as valid source wording.
def test_empty_string_does_not_count_as_valid_wording():
    provenance = [{"source_quote": ""}]
    payload = {"source_quote": ""}
    wording = resolve_source_wording(provenance, payload)
    assert wording == [None]
    assert source_wording_missing(wording) is True


# 7. Pilot exporter does not implement independent fallback logic (structural check).
def test_pilot_exporter_has_no_independent_fallback():
    import inspect
    import generate_pilot_review_batch as pilot_module
    source = inspect.getsource(pilot_module)
    assert "_rc027_note" not in source, (
        "pilot exporter must not re-implement its own RC-027 workaround now that the "
        "production ReviewService.packet() resolves source wording correctly")


# 8. Serialized packet is deterministic.
def test_packet_serialization_is_deterministic():
    if not os.path.exists(DB_PATH):
        pytest.skip("review_workbench_p56.sqlite not available")
    store = ReviewStore(DB_PATH)
    service = ReviewService(store)
    task = store.list_tasks(target_type=TargetType.CLINICAL_REGIMEN, limit=1)[0]
    p1 = service.packet(task.task_id)
    p2 = service.packet(task.task_id)
    assert p1 == p2


# 9. Stale target version is rejected (existing guarantee, re-asserted here as part of RC-027 suite).
def test_stale_target_version_rejected_still_holds():
    if not os.path.exists(DB_PATH):
        pytest.skip("review_workbench_p56.sqlite not available")
    from clinical_engine.review_workbench.models import ReviewRole
    store = ReviewStore(DB_PATH)
    service = ReviewService(store)
    task = store.list_tasks(state=ReviewState.PENDING, limit=1)[0]
    with pytest.raises(Exception):
        service.claim(task.task_id, reviewer="r1", role=ReviewRole.REVIEWER_A,
                      expected_revision=task.revision + 999)


# 10. No clinical value is modified by packet construction.
def test_packet_construction_does_not_mutate_stored_target():
    if not os.path.exists(DB_PATH):
        pytest.skip("review_workbench_p56.sqlite not available")
    store = ReviewStore(DB_PATH)
    service = ReviewService(store)
    task = store.list_tasks(target_type=TargetType.CLINICAL_REGIMEN, limit=1)[0]
    before = store.target_snapshot(task)["snapshot_hash"]
    service.packet(task.task_id)
    service.packet(task.task_id)
    after = store.target_snapshot(task)["snapshot_hash"]
    assert before == after


# --- Full-queue regression guard (mirrors RC027_ROOT_CAUSE_REPORT.md measured numbers) ---
def test_full_queue_rc027_scope_fully_resolved():
    if not os.path.exists(DB_PATH):
        pytest.skip("review_workbench_p56.sqlite not available")
    store = ReviewStore(DB_PATH)
    service = ReviewService(store)
    for tt, expected_total in ((TargetType.CLINICAL_REGIMEN, 1556),
                              (TargetType.THERAPEUTIC_OPTION, 652),
                              (TargetType.GOLDEN_CASE, 7)):
        tasks = store.list_tasks(target_type=tt, limit=10_000)
        assert len(tasks) == expected_total
        for t in tasks:
            packet = service.packet(t.task_id)
            assert any(packet["original_source_wording"]), (
                f"{tt.value} {t.task_id} has no resolved source wording (RC-027 regression)")
            assert packet["review_blocked"] is False
