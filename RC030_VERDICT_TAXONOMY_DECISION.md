# RC-030 Verdict Taxonomy — Reconciliation Decision

## Decision (owner-directed)

**Canonical stored taxonomy = `dose_verification_sandbox.validation_unit.HUMAN_FIDELITY_VERDICTS`** — the set defined two turns ago (`CORRECT_EXPLICIT_PER_DAY`, `CORRECT_EXPLICIT_PER_DOSE`, `CORRECT_FIXED_DAILY`, `CORRECT_FIXED_SINGLE`, `CORRECT_RANGE_DAILY`, `CORRECT_RANGE_SINGLE`, `WRONG_DOSE_ANCHOR`, `WRONG_SEMANTIC_MARKER`, `WRONG_FREQUENCY_LINK`, `WRONG_ALTERNATIVE`, `WRONG_AGE_GROUP`, `WRONG_TABLE_ROW`, `SOURCE_INCOMPLETE`, `SOURCE_CORRUPTED`, `TABLE_CONTEXT_REQUIRED`, `REMAINS_AMBIGUOUS`, `NOT_A_DOSABLE_REGIMEN`) — this matches the owner's list exactly, so no code change was needed to the canonical set itself.

The owner-review interface's option labels (`SOURCE_CONFIRMS_PER_DAY`, `TABLE_HEADER_CONFIRMS_PER_DAY`, ...) from the previous turn are **UI-facing action strings only** — they read well in a review form but were never meant to be a second persisted vocabulary. `dose_verification_sandbox/verdict_taxonomy.py` implements the mapping layer (`UI_ACTION_TO_CANONICAL`, `map_ui_action_to_canonical()`).

## Mapping table

| UI action (interface label) | Canonical stored verdict |
|---|---|
| `SOURCE_CONFIRMS_PER_DAY` | `CORRECT_EXPLICIT_PER_DAY` |
| `SOURCE_CONFIRMS_PER_DOSE` | `CORRECT_EXPLICIT_PER_DOSE` |
| `SOURCE_CONFIRMS_FIXED_DAILY` | `CORRECT_FIXED_DAILY` |
| `SOURCE_CONFIRMS_FIXED_SINGLE` | `CORRECT_FIXED_SINGLE` |
| `SOURCE_CONFIRMS_RANGE_DAILY` | `CORRECT_RANGE_DAILY` |
| `SOURCE_CONFIRMS_RANGE_SINGLE` | `CORRECT_RANGE_SINGLE` |
| `TABLE_HEADER_CONFIRMS_PER_DAY` | `CORRECT_EXPLICIT_PER_DAY` |
| `TABLE_HEADER_CONFIRMS_PER_DOSE` | `CORRECT_EXPLICIT_PER_DOSE` |
| `WRONG_DOSE_ANCHOR` | `WRONG_DOSE_ANCHOR` |
| `WRONG_FREQUENCY_LINK` | `WRONG_FREQUENCY_LINK` |
| `WRONG_ALTERNATIVE` | `WRONG_ALTERNATIVE` |
| `SOURCE_INCOMPLETE` | `SOURCE_INCOMPLETE` |
| `SOURCE_CORRUPTED` | `SOURCE_CORRUPTED` |
| `TABLE_CONTEXT_REQUIRED` | `TABLE_CONTEXT_REQUIRED` |
| `REMAINS_AMBIGUOUS` | `REMAINS_AMBIGUOUS` |
| `NOT_A_DOSABLE_REGIMEN` | `NOT_A_DOSABLE_REGIMEN` |

`TABLE_HEADER_CONFIRMS_*` collapses onto the same canonical `CORRECT_*` value as its non-table counterpart — the canonical taxonomy doesn't split "correct" by evidence origin; that distinction is carried separately by `evidence_level` (`TABLE_HEADER_INHERITANCE` vs. `QUOTE_EXPLICIT`, etc.), not by the verdict itself.

Three canonical values (`WRONG_SEMANTIC_MARKER`, `WRONG_AGE_GROUP`, `WRONG_TABLE_ROW`) have **no UI action mapping to them yet** — the interface's `<select>` doesn't currently offer those specific options. This is intentional, not a bug: it means the canonical set is a strict superset of what the interface can emit today, so the interface can only under-express, never invent a value outside the canonical set. A future interface revision can add UI options for these three without any further taxonomy change.

## Rejection rules (implemented, tested)

- Unknown UI action strings → `UnknownVerdictActionError`, no silent fallback.
- A module-load-time assertion checks `set(UI_ACTION_TO_CANONICAL.values()) | {the 3 unreachable canonical values} == HUMAN_FIDELITY_VERDICTS` — if either taxonomy changes independently in the future without updating the mapping, importing this module fails immediately (fail closed) rather than silently drifting.

## Schema version

`OWNER_FIDELITY_SCHEMA_VERSION = 1` (`dose_verification_sandbox/verdict_taxonomy.py`) — bump this whenever the canonical set or the mapping table changes, so stored events can declare which version produced them (see `RC030_OWNER_PILOT_CONSOLIDATION_REPORT.md` §9, `OwnerFidelityEvent.event_version`).
