# RC-030 C7 — Precision-Gate Simulation Report (Phase 26)

17 synthetic-fixture tests (`tests/dose_verification_sandbox/test_c7_precision_simulation.py`) exercised the full, already-committed C4 precision pipeline (`dose_verification_sandbox.precision_calculator`) end-to-end. All 17 pass.

## Scenarios validated

| Scenario | Result |
|---|---|
| Zero events | `precision=None`, `status=NO_EVENTS` |
| One confirming event | `status=BELOW_MINIMUM_SAMPLE` (N=1 < 30) |
| One error event | `precision=0.0` |
| All ambiguous | `precision=None`, `status=INSUFFICIENT_SCORABLE_EVENTS` |
| All source-blocked | `precision=None`, `status=INSUFFICIENT_SCORABLE_EVENTS` |
| Mixed real/test events | test events fully excluded from `reviewed_count` |
| Mixed owner/AI events | whole batch → `GOVERNANCE_BLOCKED` (not a silent partial score) |
| Superseded events | **documented current gap**, see below |
| Duplicate events | whole batch → `GOVERNANCE_BLOCKED` |
| 100% precision, N=1 | stays `BELOW_MINIMUM_SAMPLE` — never auto-qualifies on a single observation |
| 100% precision, small N (5) | stays `BELOW_MINIMUM_SAMPLE` |
| Threshold met (100%, N=30) | `status=MEETS_EXPLORATORY_THRESHOLD` — informational only, confirmed **does not** populate `TYPES_MEETING_PRECISION_THRESHOLD` |
| Confidence bound below point estimate | Wilson lower bound (90% point estimate, N=30) is meaningfully below the point estimate, confirming the conservative bound is active and non-trivial |
| Multiple semantic types | scored fully independently; neither affects the governed threshold set |
| One sufficient + one insufficient type | both computed independently; threshold set stays empty regardless |
| Full-scenario threshold-write regression | `TYPES_MEETING_PRECISION_THRESHOLD` re-checked `== set()` after every scenario above ran in sequence |
| Source inspection | `precision_calculator.py` contains no file/DB/Clinical-Engine I/O and no direct assignment to `TYPES_MEETING_PRECISION_THRESHOLD` |

## Documented current gap (not a defect introduced this turn — a known, pre-existing architectural boundary)

The "superseded events" scenario demonstrates that `compute_governed_precision()` does **not** currently resolve a supersession chain down to a single active event per validation unit before scoring — both the original and the correcting event would currently be counted. This is the same gap already recorded in `RC030_C4_ARCHITECTURE_AUDIT.md` finding #6 ("full supersession-DAG resolution... deferred"). The C7 simulation test documents the *current* behavior explicitly (`test_superseded_events_only_final_active_counted`, asserting `reviewed_count == 2`, with an inline comment stating this is not a pass/fail correctness claim) so that a future turn cannot rediscover this gap by surprise — **this must be resolved before real C7 activation**, and is listed as an open item in `RC030_C7_GATE_MATRIX.md` (Gate B).

## Result

`TYPES_MEETING_PRECISION_THRESHOLD` remained `set()` across every one of the 17 scenarios, including the most favorable ones (100% precision, large N, exploratory threshold met). The pipeline behaves as a **recommendation-only** system with no code path capable of self-activating a semantic type — confirmed by both behavioral testing and source inspection.
