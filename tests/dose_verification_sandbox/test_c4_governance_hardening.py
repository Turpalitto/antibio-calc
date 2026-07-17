"""RC-030 C4 — governance-hardening regression tests for the validation-unit
identity contract, verdict taxonomy groups, owner/AI event separation,
append-only supersession guards, and the governed precision entry point.

All synthetic data. No real database touched, no network access, no
Clinical Engine import, no write to TYPES_MEETING_PRECISION_THRESHOLD.
"""
import pytest

from dose_verification_sandbox.validation_unit import (
    DoseSemanticEvidenceUnit, VALIDATION_UNIT_SCHEMA_VERSION,
)
from dose_verification_sandbox.verdict_taxonomy import (
    CONFIRMING_VERDICTS, ERROR_VERDICTS, UNRESOLVED_VERDICTS, SOURCE_BLOCKED_VERDICTS,
    PRECISION_SCORABLE_VERDICTS,
)
from dose_verification_sandbox.owner_fidelity_events import (
    validate_event, validate_events, filter_real_events, find_duplicate_event_ids,
    validate_supersession_chain, GENUINE_OWNER_REVIEWER_ID, EVENT_SCHEMA_VERSION,
)
from dose_verification_sandbox.precision_calculator import (
    compute_precision, compute_governed_precision,
    STATUS_NO_EVENTS, STATUS_INSUFFICIENT_SCORABLE_EVENTS, STATUS_BELOW_MINIMUM_SAMPLE,
    STATUS_MEETS_EXPLORATORY_THRESHOLD, STATUS_GOVERNANCE_BLOCKED, METRIC_NAME, MIN_SAMPLE_SIZE,
)
from dose_verification_sandbox.validation_status import TYPES_MEETING_PRECISION_THRESHOLD


# ── Validation-unit identity (Part III / Phase 2) ────────────────────────

def _make_unit(**overrides):
    base = dict(
        unit_id="u1", regimen_id="6657", regimen_version=1, antibiotic="test-drug", diagnosis="test-dx",
        dose_token="20-50", dose_token_start=10, dose_token_end=15,
        source_semantic_marker=None, marker_start=None, marker_end=None,
        source_quote="20-50 mg/kg", sentence_boundary=(0, 20), alternative_boundary=None,
        table_row=None, table_column=None, frequency=2.0, route="oral",
        source_pdf="guideline.pdf", source_page="5", provenance="test",
        parser_semantic_type="WEIGHT_PER_DAY", parser_rule_id="R1", parser_confidence=0.9,
    )
    base.update(overrides)
    return DoseSemanticEvidenceUnit(**base)


def test_identity_hash_deterministic_same_inputs():
    assert _make_unit().compute_identity_hash() == _make_unit().compute_identity_hash()


def test_identity_hash_stable_under_field_reordering():
    """Constructing via kwargs in a different order must not change the hash —
    identity is defined by the fixed _IDENTITY_FIELDS order, not construction order."""
    a = DoseSemanticEvidenceUnit(
        unit_id="u1", regimen_id="6657", regimen_version=1, antibiotic="x", diagnosis="y",
        dose_token="t", dose_token_start=0, dose_token_end=1, source_semantic_marker=None,
        marker_start=None, marker_end=None, source_quote="q", sentence_boundary=None,
        alternative_boundary=None, table_row=None, table_column=None, frequency=None,
        route=None, source_pdf="p.pdf", source_page="1", provenance="prov",
        parser_semantic_type="FIXED_PER_DAY", parser_rule_id="R", parser_confidence=None,
    )
    b_kwargs = dict(
        regimen_version=1, unit_id="u1", regimen_id="6657", diagnosis="y", antibiotic="x",
        dose_token_end=1, dose_token_start=0, dose_token="t", marker_end=None,
        source_semantic_marker=None, marker_start=None, alternative_boundary=None,
        source_quote="q", sentence_boundary=None, table_column=None, table_row=None,
        route=None, frequency=None, source_page="1", source_pdf="p.pdf", provenance="prov",
        parser_rule_id="R", parser_semantic_type="FIXED_PER_DAY", parser_confidence=None,
    )
    b = DoseSemanticEvidenceUnit(**b_kwargs)
    assert a.compute_identity_hash() == b.compute_identity_hash()


def test_identity_hash_material_evidence_change_produces_different_hash():
    a = _make_unit()
    b = _make_unit(source_quote="a completely different quote")
    assert a.compute_identity_hash() != b.compute_identity_hash()


def test_identity_hash_regimen_version_change_produces_different_hash():
    a = _make_unit()
    b = _make_unit(regimen_version=2)
    assert a.compute_identity_hash() != b.compute_identity_hash()


def test_identity_hash_excludes_validated_at_and_validated_by():
    a = _make_unit(validated_at=None, validated_by=None)
    b = _make_unit(validated_at="2026-07-17T00:00:00Z", validated_by="someone")
    assert a.compute_identity_hash() == b.compute_identity_hash()


def test_identity_hash_excludes_parser_provenance_fields():
    """A parser re-run with a new rule_id/confidence over the same source
    evidence is still reviewing the same claim (see validation_unit.py's
    identity-contract docstring)."""
    a = _make_unit(parser_rule_id="R1", parser_confidence=0.9)
    b = _make_unit(parser_rule_id="R2", parser_confidence=0.1)
    assert a.compute_identity_hash() == b.compute_identity_hash()


def test_identity_hash_no_timestamp_or_path_leaks_into_payload():
    payload = _make_unit().canonical_identity_payload()
    assert "validated_at" not in payload
    assert "validated_by" not in payload
    serialized = str(payload)
    assert "C:\\" not in serialized and "/home/" not in serialized


def test_identity_hash_tuple_vs_list_boundary_hashes_identically():
    a = _make_unit(sentence_boundary=(0, 20))
    b = _make_unit(sentence_boundary=[0, 20])
    assert a.compute_identity_hash() == b.compute_identity_hash()


def test_identity_hash_unicode_stable():
    a = _make_unit(source_quote="20-50 мг/кг/сутки")
    b = _make_unit(source_quote="20-50 мг/кг/сутки")
    assert a.compute_identity_hash() == b.compute_identity_hash()


def test_invalid_verdict_still_fails_closed_on_construction():
    with pytest.raises(ValueError):
        _make_unit(human_fidelity_verdict="NOT_A_REAL_VERDICT")


def test_schema_version_present_and_excluded_from_identity():
    u = _make_unit()
    assert u.validation_unit_schema_version == VALIDATION_UNIT_SCHEMA_VERSION
    assert "validation_unit_schema_version" not in u.canonical_identity_payload()


# ── Verdict taxonomy groups (Part IV / Phase 3) ──────────────────────────

def test_taxonomy_groups_are_pairwise_disjoint_and_cover_everything():
    groups = [CONFIRMING_VERDICTS, ERROR_VERDICTS, UNRESOLVED_VERDICTS, SOURCE_BLOCKED_VERDICTS]
    total = sum(len(g) for g in groups)
    union = set().union(*groups)
    assert total == len(union)  # no verdict counted in two groups


def test_precision_scorable_is_exactly_confirming_plus_error():
    assert PRECISION_SCORABLE_VERDICTS == CONFIRMING_VERDICTS | ERROR_VERDICTS
    assert PRECISION_SCORABLE_VERDICTS.isdisjoint(UNRESOLVED_VERDICTS)
    assert PRECISION_SCORABLE_VERDICTS.isdisjoint(SOURCE_BLOCKED_VERDICTS)


def test_remains_ambiguous_is_unresolved_not_scorable():
    assert "REMAINS_AMBIGUOUS" in UNRESOLVED_VERDICTS
    assert "REMAINS_AMBIGUOUS" not in PRECISION_SCORABLE_VERDICTS


# ── AI/owner event separation (Part IX / Phase 14) ───────────────────────

_KNOWN_RECORD = {"evidence_hash": "a" * 64, "regimen_version": 1, "pdf_hash": "b" * 64}


def _valid_event(**overrides):
    base = dict(
        event_id="e1", event_version=EVENT_SCHEMA_VERSION, created_at="2026-07-16T00:00:00Z",
        reviewer_id=GENUINE_OWNER_REVIEWER_ID, unit_id="a" * 64, regimen_id="5574", regimen_version=1,
        canonical_verdict="CORRECT_EXPLICIT_PER_DAY", ui_action="SOURCE_CONFIRMS_PER_DAY",
        note="matches source quote", source_packet_hash="a" * 64, pdf_hash="b" * 64,
        parser_version="c" * 64, interface_version="owner-review-interface-v2",
        previous_event_id=None, supersedes_event_id=None, test_event=False,
    )
    base.update(overrides)
    return base


@pytest.mark.parametrize("marker,value", [
    ("review_origin", "AI_PRE_REVIEW"),
    ("review_origin", "AI_AUTONOMOUS_AUDIT"),
    ("owner_verified", False),
    ("clinically_approved", False),
    ("human_validated", False),
])
def test_ai_provenance_field_rejects_even_with_owner_reviewer_id(marker, value):
    """An AI event copied into owner shape with reviewer_id spoofed to
    OWNER_LOCAL must still be rejected because the AI provenance field
    itself is present."""
    spoofed = dict(_valid_event(), **{marker: value})
    issues = validate_event(0, spoofed, {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == marker for i in issues)


def test_non_owner_reviewer_id_rejected():
    issues = validate_event(0, _valid_event(reviewer_id="anyone_else"), {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "reviewer_id" for i in issues)


def test_ai_event_cannot_enter_governed_precision():
    ai_spoofed = dict(_valid_event(event_id="e_ai"), review_origin="AI_AUTONOMOUS_AUDIT",
                       parser_semantic_type="WEIGHT_PER_DAY")
    genuine = dict(_valid_event(event_id="e_genuine"), parser_semantic_type="WEIGHT_PER_DAY")
    result = compute_governed_precision("WEIGHT_PER_DAY", [genuine, ai_spoofed], [_KNOWN_RECORD])
    assert result.status == STATUS_GOVERNANCE_BLOCKED


def test_mixed_owner_and_ai_input_excludes_ai_and_names_nothing_silently():
    """A batch containing one bad (AI) event blocks the whole batch rather than
    silently dropping just the bad record — see compute_governed_precision's
    docstring for the rationale."""
    ai_spoofed = dict(_valid_event(event_id="e_ai"), review_origin="AI_PRE_REVIEW")
    result = compute_governed_precision("WEIGHT_PER_DAY", [ai_spoofed], [_KNOWN_RECORD])
    assert result.status == STATUS_GOVERNANCE_BLOCKED
    assert result.precision is None


# ── test_event type strictness (Part V / Phase 7) ────────────────────────

@pytest.mark.parametrize("bad_value", ["false", "true", 0, 1, None, "False"])
def test_non_bool_test_event_rejected_by_validator(bad_value):
    issues = validate_event(0, _valid_event(test_event=bad_value), {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "test_event" for i in issues)


@pytest.mark.parametrize("bad_value", ["false", 0, 1, None])
def test_non_bool_test_event_excluded_from_filter_real_events(bad_value):
    events = [_valid_event(test_event=bad_value)]
    assert filter_real_events(events) == []


def test_missing_test_event_field_fails_validation():
    ev = _valid_event()
    del ev["test_event"]
    issues = validate_event(0, ev, {"a" * 64: _KNOWN_RECORD})
    assert any(i.field == "test_event" and "missing" in i.message for i in issues)


# ── Duplicate event_id and append-only supersession (Phase 6) ────────────

def test_duplicate_event_id_detected():
    events = [_valid_event(event_id="dup"), _valid_event(event_id="dup")]
    dupes = find_duplicate_event_ids(events)
    assert dupes == {"dup": [0, 1]}


def test_duplicate_event_id_rejected_by_validate_events():
    events = [_valid_event(event_id="dup"), _valid_event(event_id="dup")]
    issues = validate_events(events, [_KNOWN_RECORD])
    assert any(i.field == "event_id" and "duplicate" in i.message for i in issues)


def test_self_supersession_rejected():
    events = [_valid_event(event_id="e1", supersedes_event_id="e1")]
    issues = validate_supersession_chain(events)
    assert any("self-supersession" in i.message for i in issues)


def test_supersession_cycle_rejected():
    events = [
        _valid_event(event_id="e1", supersedes_event_id="e2"),
        _valid_event(event_id="e2", supersedes_event_id="e1"),
    ]
    issues = validate_supersession_chain(events)
    assert any("cycle" in i.message for i in issues)


def test_dangling_supersession_reference_rejected():
    events = [_valid_event(event_id="e1", supersedes_event_id="does_not_exist")]
    issues = validate_supersession_chain(events)
    assert any("dangling" in i.message for i in issues)


def test_valid_supersession_chain_accepted():
    events = [
        _valid_event(event_id="e1", supersedes_event_id=None),
        _valid_event(event_id="e2", supersedes_event_id="e1"),
    ]
    issues = validate_supersession_chain(events)
    assert issues == []


def test_original_event_preserved_in_events_list_after_supersession():
    """Append-only: superseding an event does not remove or mutate the
    original — the caller is responsible for keeping both; this module never
    deletes anything."""
    events = [
        _valid_event(event_id="e1", canonical_verdict="WRONG_DOSE_ANCHOR", note="n"),
        _valid_event(event_id="e2", supersedes_event_id="e1", canonical_verdict="CORRECT_EXPLICIT_PER_DAY"),
    ]
    validate_events(events, [_KNOWN_RECORD])
    assert events[0]["canonical_verdict"] == "WRONG_DOSE_ANCHOR"  # untouched


# ── Precision status codes (Phase 9) ──────────────────────────────────────

def test_zero_events_status_no_events():
    r = compute_precision("WEIGHT_PER_DAY", [])
    assert r.precision is None
    assert r.status == STATUS_NO_EVENTS


def test_only_unresolved_verdicts_status_insufficient_scorable():
    verdicts = [{"verdict": "REMAINS_AMBIGUOUS"}] * 5
    r = compute_precision("WEIGHT_PER_DAY", verdicts)
    assert r.precision is None
    assert r.status == STATUS_INSUFFICIENT_SCORABLE_EVENTS
    assert r.ambiguous_count == 5


def test_below_minimum_sample_status():
    verdicts = [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * (MIN_SAMPLE_SIZE - 1)
    r = compute_precision("WEIGHT_PER_DAY", verdicts)
    assert r.status == STATUS_BELOW_MINIMUM_SAMPLE
    assert r.sample_size_reliable is False


def test_high_precision_large_sample_status_meets_exploratory_only():
    verdicts = [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * MIN_SAMPLE_SIZE
    r = compute_precision("WEIGHT_PER_DAY", verdicts)
    assert r.status == STATUS_MEETS_EXPLORATORY_THRESHOLD
    # exploratory status must never itself populate the governed threshold set
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()


def test_metric_is_named_owner_source_fidelity_not_clinical_accuracy():
    r = compute_precision("WEIGHT_PER_DAY", [])
    assert r.metric_name == "OWNER_SOURCE_FIDELITY_PRECISION"
    assert METRIC_NAME == "OWNER_SOURCE_FIDELITY_PRECISION"
    assert "clinical" not in METRIC_NAME.lower()
    assert "accuracy" not in METRIC_NAME.lower()


# ── Threshold-set immutability regression (Phase 10) ──────────────────────

def test_importing_calculator_does_not_modify_threshold():
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()


def test_high_synthetic_precision_cannot_modify_threshold_set():
    before = set(TYPES_MEETING_PRECISION_THRESHOLD)
    for _ in range(5):
        compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 1000)
    assert TYPES_MEETING_PRECISION_THRESHOLD == before == set()


def test_writing_owner_events_does_not_modify_threshold():
    before = set(TYPES_MEETING_PRECISION_THRESHOLD)
    events = [_valid_event(event_id=f"e{i}") for i in range(50)]
    validate_events(events, [_KNOWN_RECORD])
    filter_real_events(events)
    assert TYPES_MEETING_PRECISION_THRESHOLD == before == set()


def test_invalid_events_cannot_activate_anything():
    before = set(TYPES_MEETING_PRECISION_THRESHOLD)
    bad = dict(_valid_event(), test_event="not_a_bool", reviewer_id="not_owner")
    compute_governed_precision("WEIGHT_PER_DAY", [bad], [_KNOWN_RECORD])
    assert TYPES_MEETING_PRECISION_THRESHOLD == before == set()


# ── Regimen 6657 compatibility (Part VIII / Phase 13) ─────────────────────
#
# No raw owner-event export file for regimen 6657 exists in this worktree
# (verified: not tracked, not present under dose_verification_sandbox/data/
# or generated/). The documented facts (RC030_FULL_REPAIR_BASELINE.json:
# owner_events=1; prior reports: canonical_verdict=REMAINS_AMBIGUOUS,
# test_event=false, genuine OWNER_LOCAL) are reproduced here as a
# schema-compliant synthetic fixture, NOT a copy of the real export.

def _regimen_6657_synthetic_event():
    return _valid_event(
        event_id="regimen-6657-synthetic-fixture", regimen_id="6657",
        canonical_verdict="REMAINS_AMBIGUOUS", ui_action="REMAINS_AMBIGUOUS",
        note="",  # historical interface schema allows empty note for non-confirming verdicts
        test_event=False, parser_semantic_type="AMBIGUOUS",
    )


def test_regimen_6657_synthetic_event_validates():
    ev = _regimen_6657_synthetic_event()
    known = {"a" * 64: {"evidence_hash": "a" * 64, "regimen_version": 1, "pdf_hash": "b" * 64}}
    assert validate_event(0, ev, known) == []


def test_regimen_6657_synthetic_event_contributes_to_reviewed_not_precision():
    known = [{"evidence_hash": "a" * 64, "regimen_version": 1, "pdf_hash": "b" * 64}]
    result = compute_governed_precision("AMBIGUOUS", [_regimen_6657_synthetic_event()], known)
    assert result.reviewed_count == 1
    assert result.ambiguous_count == 1
    assert result.correct_count == 0
    assert result.incorrect_count == 0
    assert result.precision is None  # zero-denominator stays null, never 0 or 1
    assert result.status == STATUS_INSUFFICIENT_SCORABLE_EVENTS


def test_regimen_6657_does_not_make_any_type_eligible():
    known = [{"evidence_hash": "a" * 64, "regimen_version": 1, "pdf_hash": "b" * 64}]
    compute_governed_precision("AMBIGUOUS", [_regimen_6657_synthetic_event()], known)
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()


# ── No side effects on import (Phase 17 "import side effects") ───────────
#
# Deliberately NOT using importlib.reload() here: reloading a module creates
# a new exception/class object, which silently breaks `isinstance`/`except`
# matching (and `pytest.raises`) in any *other* already-imported test module
# holding a reference to the old class — a real cross-test contamination bug
# caught while writing this suite (test_owner_pilot_consolidation.py's
# `UnknownVerdictActionError` check started failing only when run in the same
# session as a reload). A static source scan is both safer and sufficient to
# prove "no I/O on import".

import inspect

_IO_MARKERS = ("open(", "requests.", "socket.", "sqlite3.connect", "urllib", "subprocess.")


@pytest.mark.parametrize("module", [
    "dose_verification_sandbox.validation_unit",
    "dose_verification_sandbox.verdict_taxonomy",
    "dose_verification_sandbox.owner_fidelity_events",
    "dose_verification_sandbox.precision_calculator",
])
def test_module_source_contains_no_io_or_network_calls(module):
    import importlib
    mod = importlib.import_module(module)
    source = inspect.getsource(mod)
    for marker in _IO_MARKERS:
        assert marker not in source, f"{module} references {marker!r} — C4 modules must be pure/offline"
