"""RC-030 Part III — canonical verdict taxonomy and UI-action mapping.

Owner decision (RC030_VERDICT_TAXONOMY_DECISION.md): the CANONICAL stored
verdict vocabulary is `dose_verification_sandbox.validation_unit.HUMAN_FIDELITY_VERDICTS`
(CORRECT_EXPLICIT_PER_DAY, WRONG_DOSE_ANCHOR, ...). The owner-review
interface's UI action labels (SOURCE_CONFIRMS_PER_DAY, ...) are UI-facing
only and must be deterministically mapped to a canonical value before
being persisted anywhere. No UI action string is ever persisted directly.
"""
from __future__ import annotations

from .validation_unit import HUMAN_FIDELITY_VERDICTS

OWNER_FIDELITY_SCHEMA_VERSION = 1

# Canonical taxonomy groups (single source of truth — precision_calculator.py
# and any future consumer must import these rather than re-deriving their own
# bucketing, to avoid the two drifting apart).
CONFIRMING_VERDICTS = {
    "CORRECT_EXPLICIT_PER_DAY", "CORRECT_EXPLICIT_PER_DOSE", "CORRECT_FIXED_DAILY",
    "CORRECT_FIXED_SINGLE", "CORRECT_RANGE_DAILY", "CORRECT_RANGE_SINGLE",
}
ERROR_VERDICTS = {
    "WRONG_DOSE_ANCHOR", "WRONG_SEMANTIC_MARKER", "WRONG_FREQUENCY_LINK",
    "WRONG_ALTERNATIVE", "WRONG_AGE_GROUP", "WRONG_TABLE_ROW",
}
UNRESOLVED_VERDICTS = {"REMAINS_AMBIGUOUS", "TABLE_CONTEXT_REQUIRED", "NOT_A_DOSABLE_REGIMEN"}
SOURCE_BLOCKED_VERDICTS = {"SOURCE_INCOMPLETE", "SOURCE_CORRUPTED"}

# Only confirming/error verdicts are "scorable" — they enter the precision
# calculator's denominator. Unresolved and source-blocked verdicts are
# reported separately and never counted as correct or incorrect.
PRECISION_SCORABLE_VERDICTS = CONFIRMING_VERDICTS | ERROR_VERDICTS

_TAXONOMY_GROUPS = (CONFIRMING_VERDICTS, ERROR_VERDICTS, UNRESOLVED_VERDICTS, SOURCE_BLOCKED_VERDICTS)
assert (CONFIRMING_VERDICTS | ERROR_VERDICTS | UNRESOLVED_VERDICTS | SOURCE_BLOCKED_VERDICTS
        == HUMAN_FIDELITY_VERDICTS), "verdict taxonomy groups have drifted from HUMAN_FIDELITY_VERDICTS"
assert sum(len(g) for g in _TAXONOMY_GROUPS) == len(HUMAN_FIDELITY_VERDICTS), (
    "taxonomy groups must be pairwise disjoint (a verdict appears in more than one group)"
)


class UnknownVerdictActionError(ValueError):
    """Raised when a UI action string has no canonical mapping."""


# Every UI action the owner-review interface can emit maps to exactly one
# canonical verdict. Left side = UI action (interface's own vocabulary,
# Phase 6 of the prior turn); right side = canonical stored verdict
# (validation_unit.HUMAN_FIDELITY_VERDICTS, Phase 8/9 of the turn before that).
UI_ACTION_TO_CANONICAL = {
    "SOURCE_CONFIRMS_PER_DAY": "CORRECT_EXPLICIT_PER_DAY",
    "SOURCE_CONFIRMS_PER_DOSE": "CORRECT_EXPLICIT_PER_DOSE",
    "SOURCE_CONFIRMS_FIXED_DAILY": "CORRECT_FIXED_DAILY",
    "SOURCE_CONFIRMS_FIXED_SINGLE": "CORRECT_FIXED_SINGLE",
    "SOURCE_CONFIRMS_RANGE_DAILY": "CORRECT_RANGE_DAILY",
    "SOURCE_CONFIRMS_RANGE_SINGLE": "CORRECT_RANGE_SINGLE",
    # Table-header-sourced confirmations map to the same "correct" canonical
    # value as their non-table counterpart — the canonical taxonomy does not
    # distinguish evidence origin within a CORRECT_* verdict; evidence_level
    # (a separate field) carries that distinction (TABLE_HEADER_INHERITANCE).
    "TABLE_HEADER_CONFIRMS_PER_DAY": "CORRECT_EXPLICIT_PER_DAY",
    "TABLE_HEADER_CONFIRMS_PER_DOSE": "CORRECT_EXPLICIT_PER_DOSE",
    "WRONG_DOSE_ANCHOR": "WRONG_DOSE_ANCHOR",
    "WRONG_FREQUENCY_LINK": "WRONG_FREQUENCY_LINK",
    "WRONG_ALTERNATIVE": "WRONG_ALTERNATIVE",
    "SOURCE_INCOMPLETE": "SOURCE_INCOMPLETE",
    "SOURCE_CORRUPTED": "SOURCE_CORRUPTED",
    "TABLE_CONTEXT_REQUIRED": "TABLE_CONTEXT_REQUIRED",
    "REMAINS_AMBIGUOUS": "REMAINS_AMBIGUOUS",
    "NOT_A_DOSABLE_REGIMEN": "NOT_A_DOSABLE_REGIMEN",
}

# The owner-review interface's option list also includes two UI actions with
# no direct canonical counterpart yet (WRONG_SEMANTIC_MARKER and
# WRONG_AGE_GROUP / WRONG_TABLE_ROW exist canonically but have no UI action
# emitting them today — the interface's <select> doesn't offer them). This is
# intentional and not a gap: the canonical set is a superset of what the
# current interface can emit, which is the safe direction (interface can only
# ever narrow, never invent a canonical value that doesn't exist).
_UNMAPPED_CANONICAL_NOT_YET_REACHABLE_FROM_UI = {
    "WRONG_SEMANTIC_MARKER", "WRONG_AGE_GROUP", "WRONG_TABLE_ROW",
}

assert set(UI_ACTION_TO_CANONICAL.values()) | _UNMAPPED_CANONICAL_NOT_YET_REACHABLE_FROM_UI == HUMAN_FIDELITY_VERDICTS, (
    "canonical taxonomy and mapping table have drifted apart"
)


def map_ui_action_to_canonical(ui_action: str) -> str:
    """Deterministic, total-on-known-inputs mapping. Raises on anything not
    explicitly listed — no silent fallback, no guessing."""
    if ui_action not in UI_ACTION_TO_CANONICAL:
        raise UnknownVerdictActionError(f"no canonical mapping for UI action: {ui_action!r}")
    canonical = UI_ACTION_TO_CANONICAL[ui_action]
    if canonical not in HUMAN_FIDELITY_VERDICTS:
        raise UnknownVerdictActionError(f"mapped canonical value {canonical!r} is not in HUMAN_FIDELITY_VERDICTS")
    return canonical
