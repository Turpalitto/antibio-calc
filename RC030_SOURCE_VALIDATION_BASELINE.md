# RC-030 Source Validation Baseline — Frozen 2026-07-16

Recorded before any Part III validation work begins. All numbers computed live against the current repository state; nothing here is copied from prior narrative reports without re-derivation.

## Commit / code identity

- Portability commit (current HEAD): `394818675b0ed199e03cae1d89e38a488f5102ce`
- RC-030 semantics commit: `dd8b3adad1ca60d3119ac7b48e6e50dbe364d328`
- `dose_verification_sandbox/semantics_parser.py` SHA-256: `78932988d61670744523f6879f34a35706a9ca3b22193dd5e469d2e3b217277f`
- `dose_verification_sandbox/validation_status.py` SHA-256: `71e0c6a3ca6ca74779617f642e608acdd2fb8ea9043c655fca9da14ea773954b`

## Source database hashes

- `assembled_regimens.sqlite`: `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9`
- `backups/p5_6_baseline_20260715/normalized_regimens.sqlite`: `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237`

## Corpus classification (live re-derivation, all 2,675 rows)

| semantic_type | count |
|---|---|
| MISSING | 658 |
| FIXED_PER_DOSE | 579 |
| FIXED_PER_DAY | 506 |
| WEIGHT_PER_DAY | 446 |
| AMBIGUOUS | 236 |
| NOT_APPLICABLE | 96 |
| WEIGHT_PER_DOSE | 80 |
| UNPARSED | 74 |
| **total** | **2675** |

- Parser candidates (resolvable types: `WEIGHT_PER_DAY + WEIGHT_PER_DOSE + FIXED_PER_DAY + FIXED_PER_DOSE`): **1,611** (60.2%)
- Ambiguous: **236**
- Unparsed: **74**
- Unresolvable/not-dosable (`MISSING` + `NOT_APPLICABLE`): **754**
- Max-dose signal candidates (`extract_max_dose_signal` non-null): **104**

## Eligibility (live re-derivation)

- `calculation_eligibility` distribution: **`{BLOCKED: 2675}`** — every row, no exceptions.
- Calculation eligible (non-BLOCKED): **0**
- Approved objects: **0** (`review_decisions` = 0 rows; all 9,153 `review_tasks` = `PENDING`, re-queried live)
- Clinical Engine: **disconnected** (only `evidence/generate_regimen_5574_evidence.py` references RC-030 module names outside the sandbox, and it queries databases directly, not through semantics code)

## Required baseline check

- 2,675 assembled rows — ✅ matches
- calculation eligible = 0 — ✅ matches
- approved objects = 0 — ✅ matches
- Clinical Engine disconnected — ✅ matches

This baseline is the reference point for all Part III validation work. No row's status may regress against these numbers without an explicit, documented reason.
