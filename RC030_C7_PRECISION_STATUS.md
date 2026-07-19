# RC-030 / C7 Part X-XI — Precision Calculation and Governance Gate (current state)

## Governed metric status

`compute_governed_precision(semantic_type, raw_events=[], known_records=[])` → `PrecisionResult(reviewed_count=0, precision=None, wilson_lower=None, status='NO_EVENTS')` — verified directly against the already-committed `dose_verification_sandbox/precision_calculator.py` (built in C7-ENTRY, unchanged this program). Zero real `OWNER_LOCAL` events exist, so **no metric is computed, none is fabricated**.

## Required reporting per Phase 25 (all zero, all real)

| Field | Value |
|---|---|
| reviewed_total | 0 |
| active_event_total | 0 |
| scorable_total | 0 |
| confirming_total | 0 |
| error_total | 0 |
| unresolved_total | 0 |
| source_blocked_total | 0 |
| invalid_excluded | 0 |
| test_excluded | 5 (the synthetic control events created and then cleared during Part VII browser validation — never part of governed input, listed here only for audit completeness) |
| AI_excluded | 0 |
| superseded_excluded | 0 |

## Confidence/sample-size proposals (Phase 26)

Not computable — 0 scorable events. The candidate-N tables already proposed in `RC030_C7_PRECISION_SIMULATION_REPORT.md` (from the earlier C7-ENTRY checkpoint) remain the standing proposal (N=20/30/50/74, now re-anchored against the smaller, doubly-verified 36-record exact-link pool from C6.8). No activation threshold applied automatically, per the owner's explicit prohibition.

## C7 status

**OWNER_ACTION_REQUIRED.** (See `RC030_C7_OWNER_ACTION_REQUIRED_GATE.md` for the full operational gate.)

## No automatic activation (Phase 28)

Confirmed by omission, not merely by claim: this program's commits touch `dose_verification_sandbox/`, `generated/rc030_recovery/`, `generated/rc030_c7*/`, `review_batches/`, and documentation only. `TYPES_MEETING_PRECISION_THRESHOLD`, source config, environment variables, calculation activation, Clinical Engine connection, and V6 migration are untouched — verified by the same invariant checks run at every checkpoint in this program (see final report).
