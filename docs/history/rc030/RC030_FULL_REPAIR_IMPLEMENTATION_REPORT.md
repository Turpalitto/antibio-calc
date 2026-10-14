# RC-030 Full Repair — Implementation Report

All changes are fail-closed: `TYPES_MEETING_PRECISION_THRESHOLD` stays empty, calculation-eligible stays 0/2,675, authoritative DBs untouched. Canonical suite (self-reported at implementation time): **1455 passed, 1 xfailed, 0 failures**. Sandbox suite: **151 passed** (126 existing + 25 new).

**Correction (C3 content audit):** the self-reported count above did not separate skipped tests from passed. Formally fresh-clone-verified counts are: C1 (commit `aa753317617f6871f8faff4e7c795bc920e9df75`) = 1444 passed, 11 skipped, 1 xfailed, 0 failed (1456 total); C2 (commit `35d432eddf032f4d6283bbe27f51528909b5e303`, adding the two `medical_normalizer` range tests) = 1446 passed, 11 skipped, 1 xfailed, 0 failed (1458 total). Zero failures in both cases; only the passed/skipped split was stale here.

## Files changed (tracked)

| File | Change |
|---|---|
| `dose_verification_sandbox/semantics_parser.py` | Removed the frequency==1 shortcut (Phase 2); added SINGLE (`однократно`), `р/сут`, `дважды/трижды` markers (Phases 3-4); schedule-period detection + weekly/every-other-day/every-N-hours/sub-daily guards (Phase 5); loading/maintenance guard (Phase 8); source-range-loss guard populating dose_min/max + risk flags (Phase 11) |
| `dose_verification_sandbox/semantics_models.py` | Additive fields: `schedule_period, administrations_per_day, interval_hours, schedule_risk_flags, range_min_source, range_max_source, range_collapsed_upstream`; `SCHEDULE_PERIODS`, `SCHEDULE_RISK_FLAGS` |
| `medical_normalizer/drug_parser.py` | `DoseNormalizer.parse()` now preserves the range upper bound (`match.group(2)`) into `dose_max`; `dose_value` remains byte-identical as the lower bound (Phase 9) |
| `medical_normalizer/models.py` | Additive `dose_min/dose_max/dose_is_range/dose_range_raw/dose_basis_raw/dose_source_start/dose_source_end/dose_range_confidence` + `to_dict_with_range()`; `to_dict()` unchanged so authoritative DB serialization is identical |
| `tests/dose_verification_sandbox/test_semantics_parser.py` | Updated 2 tests that asserted the removed freq==1 shortcut |

## New files (untracked)

- `tests/dose_verification_sandbox/test_deterministic_repair.py` — 25 regression tests (Phases 2-11 + normalizer)
- `dose_verification_sandbox` had earlier Part III modules from prior turns (owner_fidelity, verdict_taxonomy, etc.) — unrelated to this repair; classified separately below.

## Parser fixes implemented
1. frequency==1 no longer establishes dose basis — markerless doses stay AMBIGUOUS + EXPLICIT_DOSE_BASIS_MISSING.
2. `однократно`/`разовая доза`/`один раз` → single-administration (per-dose).
3. `р/сут`, `р./сут`, `раз/сут`, `дважды`, `трижды` frequency tokens recognized.
4. Weekly (WEEKLY_SCHEDULE_UNSUPPORTED), every-other-day (NON_DAILY_SCHEDULE), every-N-hours (interval_hours + informational admins/day), sub-daily (SUB_DAILY_FREQUENCY) — all keep calculation BLOCKED.
5. Loading+maintenance both present → LOADING_MAINTENANCE_UNRESOLVED, no auto-canonical dose.
6. Source range detected while structured scalar → RANGE_VALUE_COLLAPSED_UPSTREAM + NORMALIZER_RANGE_UPPER_BOUND_DROPPED + recovered min/max.

## Normalizer fix implemented
`DoseNormalizer.parse()` reads and preserves the previously-discarded upper bound. `dose_value` unchanged (byte-identical lower bound); `dose_max`/`dose_is_range` added. `to_dict()` untouched → authoritative DB writer unaffected.

## Range fields introduced
`dose_min, dose_max, dose_is_range, dose_range_raw, dose_basis_raw, dose_source_start, dose_source_end, dose_range_confidence` (normalizer model) + `range_min_source, range_max_source, range_collapsed_upstream` (sandbox semantics).