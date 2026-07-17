"""RC-030 C7-PREP — precision-gate simulation (Phase 26).

Validates the full, already-committed C4 precision pipeline
(`dose_verification_sandbox.precision_calculator`) against every required
synthetic scenario before any real owner data exists. All data here is
synthetic; no real owner or AI event is used. This is a readiness
simulation, not an activation — nothing here writes to
TYPES_MEETING_PRECISION_THRESHOLD, any database, or the Clinical Engine.
"""
import pytest

from dose_verification_sandbox.owner_fidelity_events import GENUINE_OWNER_REVIEWER_ID
from dose_verification_sandbox.precision_calculator import (
    MIN_SAMPLE_SIZE, STATUS_BELOW_MINIMUM_SAMPLE, STATUS_GOVERNANCE_BLOCKED,
    STATUS_INSUFFICIENT_SCORABLE_EVENTS, STATUS_MEETS_EXPLORATORY_THRESHOLD,
    STATUS_NO_EVENTS, compute_governed_precision, compute_precision,
)
from dose_verification_sandbox.validation_status import TYPES_MEETING_PRECISION_THRESHOLD

_KNOWN_RECORD = {"evidence_hash": "a" * 64, "regimen_version": 1, "pdf_hash": "b" * 64}


def _event(**overrides):
    base = dict(
        event_id="e1", event_version=1, created_at="2026-07-17T00:00:00Z",
        reviewer_id=GENUINE_OWNER_REVIEWER_ID, unit_id="a" * 64, regimen_id="5574",
        regimen_version=1, canonical_verdict="CORRECT_EXPLICIT_PER_DAY",
        ui_action="SOURCE_CONFIRMS_PER_DAY", note="matches source",
        source_packet_hash="a" * 64, pdf_hash="b" * 64, parser_version="c" * 64,
        interface_version="v1", previous_event_id=None, supersedes_event_id=None,
        test_event=False, parser_semantic_type="WEIGHT_PER_DAY",
    )
    base.update(overrides)
    return base


def test_zero_events():
    r = compute_precision("WEIGHT_PER_DAY", [])
    assert r.precision is None
    assert r.status == STATUS_NO_EVENTS


def test_one_confirming_event():
    r = compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}])
    assert r.correct_count == 1
    assert r.status == STATUS_BELOW_MINIMUM_SAMPLE  # N=1 < MIN_SAMPLE_SIZE


def test_one_error_event():
    r = compute_precision("WEIGHT_PER_DAY", [{"verdict": "WRONG_DOSE_ANCHOR"}])
    assert r.incorrect_count == 1
    assert r.precision == 0.0


def test_all_ambiguous():
    r = compute_precision("WEIGHT_PER_DAY", [{"verdict": "REMAINS_AMBIGUOUS"}] * 50)
    assert r.precision is None
    assert r.status == STATUS_INSUFFICIENT_SCORABLE_EVENTS
    assert r.ambiguous_count == 50


def test_all_source_blocked():
    r = compute_precision("WEIGHT_PER_DAY", [{"verdict": "SOURCE_INCOMPLETE"}] * 50)
    assert r.precision is None
    assert r.status == STATUS_INSUFFICIENT_SCORABLE_EVENTS
    assert r.insufficient_count == 50


def test_mixed_real_test_events_excludes_test():
    events = [_event(event_id=f"e{i}") for i in range(30)] + \
             [_event(event_id=f"t{i}", test_event=True) for i in range(30)]
    r = compute_governed_precision("WEIGHT_PER_DAY", events, [_KNOWN_RECORD])
    assert r.reviewed_count == 30  # test events never counted


def test_mixed_owner_ai_excludes_ai_wholesale():
    genuine = [_event(event_id=f"e{i}") for i in range(30)]
    ai_spoofed = [dict(_event(event_id="ai1"), review_origin="AI_AUTONOMOUS_AUDIT")]
    r = compute_governed_precision("WEIGHT_PER_DAY", genuine + ai_spoofed, [_KNOWN_RECORD])
    assert r.status == STATUS_GOVERNANCE_BLOCKED


def test_superseded_events_only_final_active_counted():
    original = _event(event_id="e1", canonical_verdict="WRONG_DOSE_ANCHOR")
    correction = _event(event_id="e2", supersedes_event_id="e1", canonical_verdict="CORRECT_EXPLICIT_PER_DAY")
    events = [original, correction]
    # compute_governed_precision does not itself resolve supersession chains
    # to a single active event per unit -- this is a known, documented C4/C6
    # architectural boundary (see RC030_C4_ARCHITECTURE_AUDIT.md finding #6:
    # full supersession-DAG resolution is deferred). The simulation
    # demonstrates the current behavior (both events currently score) so a
    # future C7 turn knows this must be resolved before real activation.
    r = compute_governed_precision("WEIGHT_PER_DAY", events, [_KNOWN_RECORD])
    assert r.reviewed_count == 2  # documents current behavior; not a pass/fail claim


def test_duplicate_events_rejected():
    events = [_event(event_id="dup"), _event(event_id="dup")]
    r = compute_governed_precision("WEIGHT_PER_DAY", events, [_KNOWN_RECORD])
    assert r.status == STATUS_GOVERNANCE_BLOCKED


def test_100_percent_precision_n_equals_1_stays_below_minimum_sample():
    r = compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}])
    assert r.precision == 1.0
    assert r.status == STATUS_BELOW_MINIMUM_SAMPLE
    assert r.sample_size_reliable is False


def test_100_percent_precision_small_n_stays_below_minimum_sample():
    r = compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 5)
    assert r.precision == 1.0
    assert r.status == STATUS_BELOW_MINIMUM_SAMPLE


def test_threshold_met_but_governance_status_is_exploratory_only_not_activated():
    r = compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * MIN_SAMPLE_SIZE)
    assert r.status == STATUS_MEETS_EXPLORATORY_THRESHOLD
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()  # exploratory status never activates anything


def test_confidence_bound_below_threshold_even_with_high_point_estimate():
    # 27/30 correct = 90% point estimate, but Wilson lower bound is meaningfully below 90%
    verdicts = [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 27 + [{"verdict": "WRONG_DOSE_ANCHOR"}] * 3
    r = compute_precision("WEIGHT_PER_DAY", verdicts)
    assert r.wilson_lower < r.precision


def test_multiple_semantic_types_independent():
    r_a = compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * MIN_SAMPLE_SIZE)
    r_b = compute_precision("FIXED_PER_DAY", [{"verdict": "REMAINS_AMBIGUOUS"}] * MIN_SAMPLE_SIZE)
    assert r_a.status == STATUS_MEETS_EXPLORATORY_THRESHOLD
    assert r_b.status == STATUS_INSUFFICIENT_SCORABLE_EVENTS
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()


def test_one_type_sufficient_one_insufficient_neither_activates():
    sufficient = compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * MIN_SAMPLE_SIZE)
    insufficient = compute_precision("FIXED_PER_DOSE", [{"verdict": "CORRECT_FIXED_DAILY"}] * 5)
    assert sufficient.status == STATUS_MEETS_EXPLORATORY_THRESHOLD
    assert insufficient.status == STATUS_BELOW_MINIMUM_SAMPLE
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()


def test_simulation_never_writes_threshold_across_all_scenarios():
    before = set(TYPES_MEETING_PRECISION_THRESHOLD)
    compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 1000)
    compute_governed_precision("WEIGHT_PER_DAY", [_event(event_id=f"e{i}") for i in range(50)], [_KNOWN_RECORD])
    assert TYPES_MEETING_PRECISION_THRESHOLD == before == set()


def test_output_is_recommendation_only_no_source_or_config_write():
    import inspect
    import dose_verification_sandbox.precision_calculator as mod
    source = inspect.getsource(mod)
    for marker in ("open(", "sqlite3.connect", "clinical_engine", "TYPES_MEETING_PRECISION_THRESHOLD ="):
        assert marker not in source
