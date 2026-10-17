# RC-030 / C7 — Phase 0 Baseline Freeze

Machine-readable twin: [RC030_C7_OWNER_REVIEW_BASELINE.json](RC030_C7_OWNER_REVIEW_BASELINE.json)

## Git state

- HEAD: `208f4d94808f8865973d3adc1472bd835bc206f2`. The spec's "expected current HEAD" (`0cec60c`) is C6.8-D; actual HEAD is one commit later — `208f4d9`, the C6.8 final report/verdict document committed immediately after C6.8-D in the prior turn. Chain re-verified intact and in order: `3351833` (C6.8-A) → `cbafb2a` (C6.8-B) → `fd350c1` (C6.8-C) → `0cec60c` (C6.8-D) → `208f4d9` (final report).
- `origin/main`: 29 commits ahead, 0 behind.
- Staging area: empty.

## Code hashes (sha256, first 16 shown; full in JSON twin)

| File | Hash |
|---|---|
| `dose_verification_sandbox/dose_unit_signature.py` | `6ba1f5bec802ee46` |
| `dose_verification_sandbox/span_attribution.py` | `473a466ceffa063f` |
| `dose_verification_sandbox/owner_fidelity_events.py` | `498e16a69e41f47d` (unchanged since C6.7) |
| `dose_verification_sandbox/verdict_taxonomy.py` | `029f3b0dd02872e7` (unchanged since C6.7) |
| `generated/rc030_recovery/build_interface.py` | `7e92da0d86575996` |
| `generated/rc030_recovery/owner_review_template.html` | `1e3e8595e83c295a` |

## C6.8 queue hashes

All 6 queues (`RC030_C68_EXACT_LINK_OWNER_QUEUE.json`, `_SINGLE_CANDIDATE_QUEUE.json`, `_UNIT_BASIS_QUEUE.json`, `_SOURCE_DEFECT_QUEUE.json`, `_TABLE_REVIEW_QUEUE.json`, `_ENGINE_REVIEW_QUEUE.json`) hashed — full values in JSON twin.

## V6 hash

`generated/rc030_range_rebuild_v6/assembled_regimens_range_v6.sqlite` = `7e2c4d8057ba848e...` — matches the C6.8 final report exactly.

## Database state — unchanged from C6.8

| DB | Hash | State |
|---|---|---|
| `assembled_regimens.sqlite` | `9f505d08428cd284...` | 2675 rows, 0 approved |
| `review_workbench_p56.sqlite` | `3e479ee70e59ce9a...` | 9153/9153 PENDING, 0 decisions, 0 registered reviewers |
| `kb_final.db` | `16c31fba2ecafbb9...` | unchanged |

## Governance invariants — all required to match, verified directly

| Invariant | Required | Observed | Status |
|---|---|---|---|
| assembled = 2675 | 2675 | 2675 | ✅ |
| eligible = 0 | 0 | 0 | ✅ |
| approved = 0 | 0 | 0 | ✅ |
| threshold = set() | empty | empty | ✅ |
| review_decisions = 0 | 0 | 0 | ✅ |
| review_tasks PENDING | 9153 | 9153 | ✅ |
| registered reviewers | 0 | 0 | ✅ |
| Clinical Engine disconnected | yes | yes | ✅ |
| staging area empty | yes | yes | ✅ |

## Invariant check result

**ALL_BASELINE_INVARIANTS_MATCH_EXPECTED.** No mismatch. Proceeding to Part II (queue reconciliation).
