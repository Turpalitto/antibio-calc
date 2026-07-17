"""RC-030 Owner Pilot Consolidation — verdict taxonomy, event validation,
and precision-pipeline dry-run tests. All synthetic data; no real database
touched; no real owner verdicts exist anywhere in this suite.
"""
import pytest

from dose_verification_sandbox.verdict_taxonomy import (
    map_ui_action_to_canonical, UnknownVerdictActionError, UI_ACTION_TO_CANONICAL,
)
from dose_verification_sandbox.validation_unit import HUMAN_FIDELITY_VERDICTS
from dose_verification_sandbox.owner_fidelity_events import (
    validate_event, validate_events, filter_real_events, EVENT_SCHEMA_VERSION,
)
from dose_verification_sandbox.precision_calculator import compute_precision
from dose_verification_sandbox.validation_status import TYPES_MEETING_PRECISION_THRESHOLD


# ── Verdict taxonomy reconciliation ──────────────────────────────────

def test_every_ui_action_maps_to_a_canonical_verdict():
    for ui_action in UI_ACTION_TO_CANONICAL:
        canonical = map_ui_action_to_canonical(ui_action)
        assert canonical in HUMAN_FIDELITY_VERDICTS


def test_unknown_ui_action_rejected():
    with pytest.raises(UnknownVerdictActionError):
        map_ui_action_to_canonical("MADE_UP_ACTION")


def test_table_header_confirms_maps_to_same_canonical_as_source_confirms():
    assert map_ui_action_to_canonical("TABLE_HEADER_CONFIRMS_PER_DAY") == map_ui_action_to_canonical("SOURCE_CONFIRMS_PER_DAY")


# ── OwnerFidelityEvent validation ────────────────────────────────────

_KNOWN_RECORD = {"evidence_hash": "a" * 64, "regimen_version": 1, "pdf_hash": "b" * 64}


def _valid_event(**overrides):
    base = dict(
        event_id="e1", event_version=EVENT_SCHEMA_VERSION, created_at="2026-07-16T00:00:00Z",
        reviewer_id="OWNER_LOCAL", unit_id="a" * 64, regimen_id="5574", regimen_version=1,
        canonical_verdict="CORRECT_EXPLICIT_PER_DAY", ui_action="SOURCE_CONFIRMS_PER_DAY",
        note="matches source quote", source_packet_hash="a" * 64, pdf_hash="b" * 64,
        parser_version="c" * 64, interface_version="owner-review-interface-v2",
        previous_event_id=None, supersedes_event_id=None, test_event=True,
    )
    base.update(overrides)
    return base


def test_valid_event_passes():
    issues = validate_event(0, _valid_event(), {"a" * 64: _KNOWN_RECORD})
    assert issues == []


def test_stale_regimen_version_rejected():
    issues = validate_event(0, _valid_event(regimen_version=2), {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "regimen_version" for i in issues)


def test_pdf_hash_mismatch_rejected():
    issues = validate_event(0, _valid_event(pdf_hash="f" * 64), {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "pdf_hash" for i in issues)


def test_unknown_source_packet_hash_rejected():
    issues = validate_event(0, _valid_event(source_packet_hash="d" * 64), {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "source_packet_hash" for i in issues)


def test_unsupported_schema_version_rejected():
    issues = validate_event(0, _valid_event(event_version=99), {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "event_version" for i in issues)


def test_confirming_verdict_without_note_rejected():
    issues = validate_event(0, _valid_event(note=""), {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "note" for i in issues)


def test_non_confirming_verdict_without_note_allowed():
    issues = validate_event(0, _valid_event(canonical_verdict="REMAINS_AMBIGUOUS", note=""), {"a" * 64: _KNOWN_RECORD})
    assert issues == []


def test_unknown_canonical_verdict_rejected():
    issues = validate_event(0, _valid_event(canonical_verdict="NOT_A_REAL_VERDICT"), {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "canonical_verdict" for i in issues)


def test_missing_required_field_rejected():
    ev = _valid_event()
    del ev["pdf_hash"]
    issues = validate_event(0, ev, {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "pdf_hash" and "missing" in i.message for i in issues)


def test_validate_events_aggregates_across_list():
    events = [_valid_event(), _valid_event(event_id="e2", regimen_version=99)]
    issues = validate_events(events, [_KNOWN_RECORD])
    assert len(issues) == 1


# ── test_event exclusion (safety-critical) ───────────────────────────

def test_filter_real_events_excludes_test_events():
    events = [_valid_event(test_event=True), _valid_event(test_event=False)]
    real = filter_real_events(events)
    assert len(real) == 1
    assert real[0]["test_event"] is False


def test_filter_real_events_excludes_events_missing_test_event_flag():
    ev = _valid_event()
    del ev["test_event"]
    assert filter_real_events([ev]) == []  # fail-closed: missing flag treated as test


# ── Precision pipeline dry run (synthetic only — no real verdicts exist) ──

def test_precision_dry_run_empty_real_store_produces_no_claim():
    synthetic_events = [_valid_event(test_event=True) for _ in range(20)]
    real = filter_real_events(synthetic_events)
    assert real == []
    result = compute_precision("WEIGHT_PER_DAY", [])
    assert result.precision is None
    assert result.reviewed_count == 0


def test_precision_dry_run_never_activates_a_semantic_type():
    before = set(TYPES_MEETING_PRECISION_THRESHOLD)
    verdicts = [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 100
    result = compute_precision("WEIGHT_PER_DAY", verdicts)
    assert result.precision is not None
    assert TYPES_MEETING_PRECISION_THRESHOLD == before == set()


def test_precision_calculator_consumes_canonical_verdicts_not_ui_actions():
    """Regression test for a real bug found while writing this suite:
    precision_calculator.py originally bucketed verdicts using the
    owner-review interface's UI action vocabulary (SOURCE_CONFIRMS_PER_DAY)
    instead of the canonical stored taxonomy (CORRECT_EXPLICIT_PER_DAY)
    established in RC030_VERDICT_TAXONOMY_DECISION.md. A raw UI action
    string must never be counted as correct; only mapped canonical verdicts
    may be."""
    ui_action_only = [{"verdict": "SOURCE_CONFIRMS_PER_DAY"}] * 10
    result = compute_precision("WEIGHT_PER_DAY", ui_action_only)
    assert result.correct_count == 0  # UI action string is not a canonical verdict
    assert result.precision is None  # nothing resolved — denominator is empty

    canonical = [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 10
    result2 = compute_precision("WEIGHT_PER_DAY", canonical)
    assert result2.correct_count == 10
    assert result2.precision == 1.0
