# RC-030 Fail-Closed Implementation Audit

Generated: 2026-07-16. Scope: verify directly in code (not documentation) that RC-030 semantics cannot become calculation-eligible on parser output alone.

## Checks and evidence

**Parser output starts UNVALIDATED.**
`dose_verification_sandbox/validation_status.py:76,80` — for any `semantic_type` in `_UNRESOLVABLE` (`UNPARSED, AMBIGUOUS, MISSING, NOT_APPLICABLE`), `validation_status = "AMBIGUOUS"` or `"UNVALIDATED"`. Confirmed.

**Unvalidated semantics have `calculation_eligibility = BLOCKED`.**
`validation_status.py:38` — `TYPES_MEETING_PRECISION_THRESHOLD: set[str] = set()` is intentionally empty (no semantic type has cleared the Wilson-95%-lower-bound 99% precision bar). Every branch of `validate()` (lines 77, 81, 86, 92) computes `calculation_eligibility` as either the literal `"BLOCKED"` or `"QA_ELIGIBLE" if ds.semantic_type in TYPES_MEETING_PRECISION_THRESHOLD else "BLOCKED"`. Since the set is empty, **every code path currently resolves to `BLOCKED`**. Confirmed by direct code read, not by trusting the docstring.

**Frequency text alone cannot establish per-day semantics.**
`semantics_parser.py:250-260` — the only place frequency is used to *infer* a time denominator is the explicit, narrow case `time_denom is None and frequency == 1.0 and dose_token_located`, justified because per-dose and per-day are algebraically identical when frequency=1 (not a guess). All other ambiguous-period cases hit `calculator.py:23-30`, which sets `calculation_status = BLOCKED` with warning `AMBIGUOUS_PERIOD`. Confirmed.

**Frequency < 1/day is blocked.**
`calculator.py:32-45` (new in the working diff) — `if expr.frequency is not None and expr.frequency < 1: trace.calculation_status = BLOCKED`, with warning `SUB_DAILY_FREQUENCY`. This is the fix for the regimen-5376 bug (daily÷frequency producing a single dose larger than the daily total). Verified present and reachable before any arithmetic step executes.

**Missing dose token is blocked.**
`semantics_parser.py:211-228` — an empty regimen row (no dose, no unit, no frequency, no duration) is classified `NOT_APPLICABLE`; anything else the parser can't interpret is classified `semantic_type="UNPARSED"`. Both land in `_UNRESOLVABLE` in `validation_status.py`, forcing `BLOCKED`. Confirmed. Also directly enforced in `calculator.py:18-21` (`parser_status == UNPARSED` → `BLOCKED`, warning `DOSE_UNPARSED`).

**Ambiguous alternatives are blocked.**
`semantics_parser.py:132-157` — when both a per-dose marker and a plain per-day marker are found with overlapping spans, the function reports `ambiguity_status` rather than silently picking one; `validation_status.py:76` maps `semantic_type == "AMBIGUOUS"` to `validation_status = "AMBIGUOUS"`, `calculation_eligibility = "BLOCKED"`. Confirmed.

**Clinical Engine cannot consume semantics.**
`grep -rl "semantics_parser\|semantics_integration\|dose_verification_sandbox"` across the repo outside `dose_verification_sandbox/` and its test directory returns only `evidence/generate_regimen_5574_evidence.py`, which queries the raw sqlite databases directly and does not import any RC-030 semantics module. Nothing under `clinical_engine/` references RC-030 code. Confirmed — no import edge exists.

**Approved state cannot change.**
`review_workbench_p56.sqlite` queried live: `review_decisions` table has 0 rows; all 9,153 `review_tasks` rows are `lifecycle_state = PENDING` with an empty `decision` column. RC-030 code contains no writer to this database (`grep` for `review_workbench_p56` inside `dose_verification_sandbox/` returns nothing). Confirmed — RC-030 has no path to touch the approval store.

**Sandbox Commit A still works without semantics files.**
`dose_verification_sandbox` targeted suite passes standalone (`96 passed`), and `calculator.py`'s pre-existing `UNPARSED`/`AMBIGUOUS_PERIOD` guards (present before this diff) do not import any of the new semantics_*.py modules — `calculate()` only imports from `.models`. Confirmed via `git diff` (no new imports added to `calculator.py`) and full-suite pass (1455 passed / 1 xfailed / 0 failed).

## Search: every path that could flip `calculation_status` BLOCKED → non-BLOCKED

`grep -n "calculation_status\s*="` across `dose_verification_sandbox/*.py` returns 6 assignment sites:
- `calculator.py:16` — initializes to `OK` at trace creation (before any semantic check runs)
- `calculator.py:19, 24, 40` — three guard clauses, all set `BLOCKED` and `return` immediately (no code after them in the same call can un-set it)
- `semantics_integration.py:57-60` — `if status == INELIGIBLE_BLOCKED and trace.calculation_status == OK: trace.calculation_status = BLOCKED` (only ever tightens `OK`→`BLOCKED`, never loosens `BLOCKED`→`OK`)
- `verify.py:27,44,51` — read-only checks (`if trace.calculation_status == BLOCKED:`), no assignment

**No code path resets `calculation_status` from `BLOCKED` back to `OK`.** The only place `OK` is ever assigned is the initial trace construction, before any semantic gate runs.

## Verdict

All eight fail-closed invariants hold under direct code inspection. No execution path was found that promotes RC-030 output to calculation-eligible.
