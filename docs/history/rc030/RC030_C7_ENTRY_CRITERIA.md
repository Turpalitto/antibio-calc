# RC-030 C7 — Entry Criteria (Phase 25)

C7 (governed precision-gate activation) may not begin until **all** of the following hold. None hold today — this document defines the gate, it does not claim readiness.

| # | Criterion | Current status |
|---|---|---|
| 1 | Genuine owner events exist | **NOT MET** — 0 genuine `OWNER_LOCAL` events exist anywhere in this repository or worktree (confirmed absent in C4/C5/C6 baselines) |
| 2 | Owner events validate under the committed C4 validator (`dose_verification_sandbox.owner_fidelity_events.validate_event`/`validate_events`) | N/A — no events exist to validate yet |
| 3 | AI events are excluded from owner precision input | **MET at the code level** — `owner_fidelity_events.py` rejects `review_origin`/`owner_verified`/`clinically_approved`/`human_validated` fields and non-`OWNER_LOCAL` `reviewer_id`, regression-tested in C4/C5 |
| 4 | Test events (`test_event=true`) are excluded | **MET at the code level** — `filter_real_events()` requires strict `test_event is False`, regression-tested |
| 5 | Supersession chains are valid (no self-supersession, no cycles, no dangling references) | **MET at the code level** — `validate_supersession_chain()`, regression-tested in C4 |
| 6 | Enough scorable events exist per semantic type (minimum sample N) | **NOT MET** — 0 events of any kind exist; `MIN_SAMPLE_SIZE = 30` is defined in `precision_calculator.py` but has never been exercised against real data |
| 7 | Unresolved events are reported separately from the precision numerator/denominator | **MET at the code level** — `ambiguous_count`/`insufficient_count` are separate fields, never folded into `correct`/`incorrect`, regression-tested |
| 8 | Minimum sample N is defined | **MET** — `MIN_SAMPLE_SIZE = 30` (`dose_verification_sandbox/precision_calculator.py`); this is a code default, not yet an owner-ratified governance threshold (see `RC030_C7_OWNER_VALIDATION_PLAN.md`) |
| 9 | Precision threshold is defined | **PARTIAL** — `_EXPLORATORY_PRECISION_THRESHOLD = 0.95` exists as an *informational* status boundary (`STATUS_MEETS_EXPLORATORY_THRESHOLD`); it is explicitly documented as never sufficient on its own to populate `TYPES_MEETING_PRECISION_THRESHOLD` |
| 10 | Confidence-bound method is defined | **MET** — `wilson_interval()` (95% Wilson score interval) exists and is tested in `precision_calculator.py`/its test suite |
| 11 | No semantic type is auto-activated | **MET** — `TYPES_MEETING_PRECISION_THRESHOLD` is a manually-edited Python constant; no code path anywhere in the repository assigns to it (grep-verified across C4/C5/C6/C6.1) |
| 12 | Owner approves threshold review | **NOT MET** — no owner approval process for threshold changes has occurred; this document proposes options only (see `RC030_C7_OWNER_VALIDATION_PLAN.md`) |
| 13 | Clinical Engine remains disconnected during C7 measurement | **MET** — disconnected throughout this entire program (re-verified every turn) |

## Summary

**5 of 13 criteria are unambiguously not yet met** (1, 2, 6, 9-partial, 12), all of which require **real owner review activity** that has not happened — this is expected: C7 readiness *preparation* (this document, the simulation, the validation plan, the gate matrix) can be completed entirely with synthetic data and existing infrastructure, but actual C7 *entry* requires the owner to conduct genuine review sessions, which is explicitly out of this turn's authorization ("The owner does NOT authorize... treating AI labels as OWNER_LOCAL" and no owner review was performed this turn).

**C7 does not begin as a result of this document.** This document only defines the gate.
