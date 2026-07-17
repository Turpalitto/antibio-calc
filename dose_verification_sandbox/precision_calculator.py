"""RC-030 Part III — deterministic precision calculation from owner fidelity
verdicts (once they exist). Never run against real data in this turn: no
human fidelity verdicts have been recorded. This module is safe to import
and test on synthetic data now; it does not read or write any real
database, and it never mutates `TYPES_MEETING_PRECISION_THRESHOLD`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .owner_fidelity_events import GENUINE_OWNER_REVIEWER_ID, filter_real_events, validate_events
from .verdict_taxonomy import CONFIRMING_VERDICTS as _CORRECT_VERDICTS
from .verdict_taxonomy import ERROR_VERDICTS as _INCORRECT_VERDICTS
from .verdict_taxonomy import SOURCE_BLOCKED_VERDICTS as _INSUFFICIENT_VERDICTS
from .verdict_taxonomy import UNRESOLVED_VERDICTS as _AMBIGUOUS_VERDICTS

MIN_SAMPLE_SIZE = 30  # below this, Wilson bounds are reported but flagged unreliable

# The metric this module computes is deliberately NOT called "clinical
# accuracy" or "parser accuracy" anywhere in this codebase — it measures
# whether an owner reviewer's source-fidelity check agreed with the parser's
# structured claim, nothing about whether the resulting dose is clinically
# correct or safe to calculate from. See RC030_DOSE_SEMANTICS_ARCHITECTURE_DECISION.md.
METRIC_NAME = "OWNER_SOURCE_FIDELITY_PRECISION"

# Per-semantic-type governance status. MEETS_EXPLORATORY_THRESHOLD is
# informational only — it is never used to populate
# validation_status.TYPES_MEETING_PRECISION_THRESHOLD, which stays a
# manually, separately owner-approved constant (see
# RC030_C4_ARCHITECTURE_AUDIT.md Phase 10).
STATUS_NO_EVENTS = "NO_EVENTS"
STATUS_INSUFFICIENT_SCORABLE_EVENTS = "INSUFFICIENT_SCORABLE_EVENTS"
STATUS_BELOW_MINIMUM_SAMPLE = "BELOW_MINIMUM_SAMPLE"
STATUS_BELOW_PRECISION_THRESHOLD = "BELOW_PRECISION_THRESHOLD"
STATUS_MEETS_EXPLORATORY_THRESHOLD = "MEETS_EXPLORATORY_THRESHOLD"
STATUS_GOVERNANCE_BLOCKED = "GOVERNANCE_BLOCKED"
STATUS_ELIGIBLE_FOR_OWNER_GATE_REVIEW = "ELIGIBLE_FOR_OWNER_GATE_REVIEW"

# Exploratory-only threshold used solely to select STATUS_MEETS_EXPLORATORY_THRESHOLD
# for reporting. This constant has no write path to TYPES_MEETING_PRECISION_THRESHOLD;
# activating a real type requires a separate, explicit, owner-approved commit.
_EXPLORATORY_PRECISION_THRESHOLD = 0.95

# Per RC030_VERDICT_TAXONOMY_DECISION.md: precision is computed over the
# CANONICAL stored taxonomy (validation_unit.HUMAN_FIDELITY_VERDICTS), never
# over the owner-review interface's raw UI action strings — a
# `verdict_taxonomy.map_ui_action_to_canonical()` call must happen before
# any verdict reaches this module.

from .validation_unit import HUMAN_FIDELITY_VERDICTS as _HUMAN_FIDELITY_VERDICTS

assert (_CORRECT_VERDICTS | _INCORRECT_VERDICTS | _AMBIGUOUS_VERDICTS | _INSUFFICIENT_VERDICTS
        == _HUMAN_FIDELITY_VERDICTS), "precision_calculator's verdict buckets have drifted from the canonical taxonomy"


@dataclass
class PrecisionResult:
    semantic_type: str
    metric_name: str = field(default=METRIC_NAME)
    reviewed_count: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    ambiguous_count: int = 0
    insufficient_count: int = 0
    precision: float | None = None
    wilson_lower: float | None = None
    wilson_upper: float | None = None
    sample_size_reliable: bool = False
    status: str = STATUS_NO_EVENTS
    error_categories: dict[str, int] = field(default_factory=dict)


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """95% Wilson score interval. Deterministic, no randomness, no external calls."""
    if n == 0:
        return (0.0, 0.0)
    p_hat = successes / n
    denom = 1 + z * z / n
    center = p_hat + z * z / (2 * n)
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n)
    lower = (center - margin) / denom
    upper = (center + margin) / denom
    return (max(0.0, lower), min(1.0, upper))


def compute_precision(semantic_type: str, verdicts: list[dict]) -> PrecisionResult:
    """`verdicts` is a list of {"verdict": str, "parser_semantic_type": str, ...} dicts,
    already filtered to `parser_semantic_type == semantic_type` by the caller.
    Records with unresolved-only verdicts (ambiguous/insufficient) are NEVER
    counted as correct — they are excluded from the precision denominator
    entirely, per the mission's explicit rule."""
    correct = sum(1 for v in verdicts if v["verdict"] in _CORRECT_VERDICTS)
    incorrect = sum(1 for v in verdicts if v["verdict"] in _INCORRECT_VERDICTS)
    ambiguous = sum(1 for v in verdicts if v["verdict"] in _AMBIGUOUS_VERDICTS)
    insufficient = sum(1 for v in verdicts if v["verdict"] in _INSUFFICIENT_VERDICTS)

    resolved = correct + incorrect  # denominator excludes ambiguous/insufficient
    precision = (correct / resolved) if resolved > 0 else None
    if resolved > 0:
        lower, upper = wilson_interval(correct, resolved)
    else:
        lower = upper = None

    error_categories: dict[str, int] = {}
    for v in verdicts:
        if v["verdict"] in _INCORRECT_VERDICTS:
            error_categories[v["verdict"]] = error_categories.get(v["verdict"], 0) + 1

    sample_size_reliable = resolved >= MIN_SAMPLE_SIZE
    if len(verdicts) == 0:
        status = STATUS_NO_EVENTS
    elif resolved == 0:
        status = STATUS_INSUFFICIENT_SCORABLE_EVENTS
    elif not sample_size_reliable:
        status = STATUS_BELOW_MINIMUM_SAMPLE
    elif precision is not None and precision >= _EXPLORATORY_PRECISION_THRESHOLD:
        status = STATUS_MEETS_EXPLORATORY_THRESHOLD
    else:
        status = STATUS_BELOW_PRECISION_THRESHOLD

    return PrecisionResult(
        semantic_type=semantic_type,
        reviewed_count=len(verdicts),
        correct_count=correct,
        incorrect_count=incorrect,
        ambiguous_count=ambiguous,
        insufficient_count=insufficient,
        precision=precision,
        wilson_lower=lower,
        wilson_upper=upper,
        sample_size_reliable=sample_size_reliable,
        status=status,
        error_categories=error_categories,
    )


def compute_governed_precision(semantic_type: str, raw_events: list[dict], known_records: list[dict]) -> PrecisionResult:
    """Safe entry point: validates and filters `raw_events` internally before
    scoring, instead of trusting the caller to have already run
    `owner_fidelity_events.validate_events`/`filter_real_events`. This closes
    the defense-in-depth gap where `compute_precision` alone would silently
    trust whatever `verdicts` list it was handed, including AI or test
    events, if a caller forgot the filtering step.

    Any structurally invalid event (per `validate_events`, including AI
    provenance markers, non-OWNER_LOCAL reviewer_id, or a non-bool
    `test_event`) makes the whole batch's status GOVERNANCE_BLOCKED rather
    than silently dropping just the bad record — a malformed export is a
    reason to stop and look, not to compute a probably-wrong precision
    number from whatever survived filtering."""
    issues = validate_events(raw_events, known_records)
    if issues:
        return PrecisionResult(semantic_type=semantic_type, status=STATUS_GOVERNANCE_BLOCKED)

    real_events = filter_real_events(raw_events)
    same_type = [
        {"verdict": e["canonical_verdict"], "parser_semantic_type": e.get("parser_semantic_type")}
        for e in real_events
        if e.get("parser_semantic_type") == semantic_type and e["reviewer_id"] == GENUINE_OWNER_REVIEWER_ID
    ]
    return compute_precision(semantic_type, same_type)
