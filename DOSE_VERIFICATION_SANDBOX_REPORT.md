# DOSE_VERIFICATION_SANDBOX_REPORT.md

Date: 2026-07-15/16
Scope: P5.6 Dose Calculation Verification Sandbox

## Summary of work

| Phase | Output | Status |
|---|---|---|
| 0 | `DOSE_VERIFICATION_SANDBOX_AUDIT.md` | Done — corrected an inaccurate first-pass claim (no ClinicalRegimen/TherapeuticOption rows in kb_p44.db; real data lives in `assembled_regimens.sqlite`, live-verified) |
| 1 | Isolated `dose_verification_sandbox/` package + `ui/` static page, no server, no writes | Done, verified by `test_invariants.py` |
| 2 | `DoseVerificationInput` + validation, `UNSUPPORTED_INPUT` | Done |
| 3 | `snapshot.py`, diagnosis → antibiotic → regimen-variant selector (all candidates, none merged) | Done |
| 4 | `DoseExpression` + `parser.py` | Done |
| 5 | `DoseCalculationTrace` + `calculator.py` | Done |
| 6 | Range preservation | Done (synthetic — no real ranges in source schema) |
| 7 | Max-dose handling, explicit, source-backed only | Done (`MAX_DOSE_NOT_AVAILABLE` on all real data — no source columns) |
| 8 | Rounding policy | Done — `DOSE_ROUNDING_POLICY.md`, `NO_ROUNDING`/`NOT_APPLIED` only |
| 9 | Formulation conversion | `convert_to_volume()` implemented + tested; `NOT_AVAILABLE` on all real data — no source columns |
| 10 | `DoseVerificationResult`, 8 verdicts, `clinical_approval` hard-locked `NOT_APPROVED` | Done |
| 11 | `OwnerComparison` | Done |
| 12 | `DoseCalculationIssue` + local append-only log | Done — 12 real issues filed |
| 13 | `ui/dose_verification_sandbox.html` | Done, exercised live in a browser (see below) |
| 14 | Test matrix | 26 scenarios, `tests/dose_verification_sandbox/` — 45 tests, all pass |
| 15 | Real-data pilot | Done — `data/pilot_report.json`/`.md`, 12 cases |
| 16 | Golden Calculation Dataset | Done — `data/golden_calculation_dataset.json`, 4 `CALCULATION_VERIFIED` cases, all pass |
| 17 | Documentation | This file + SPEC + TRACE_SPEC + ROUNDING_POLICY + USER_GUIDE; `ROOT_CAUSE_REGISTER.md` updated (RC-030); `PROJECT_STATE.md`/`NEXT_TASK.md`/`AI_LOG.md` updated |

## Real-data pilot result (Phase 15)

12 cases selected read-only from `assembled_regimens.sqlite` (5 pediatric mg/kg regimens, 5 adult
fixed-mg regimens, 2 intentionally-compound-unit regimens). Suggested categories with **zero
available real cases**, reported honestly rather than padded: dose-range (0 — no range columns
exist), max-dose (0 — no max-dose columns exist), formulation-conversion (0 — no concentration
columns exist).

**Result: 12/12 cases resolved to `calculation_status = BLOCKED`.** 10 via `AMBIGUOUS_PERIOD` (the
`mg`/`mg/kg` unit strings don't say per-dose vs per-day), 2 via `DOSE_UNPARSED` (compound unit
strings like `"г; мг/кг"`). This is filed as **RC-030** in `ROOT_CAUSE_REGISTER.md` — a genuine
upstream schema gap in the P5.3 Regimen Assembly Engine, not a sandbox defect. All 12 cases are
recorded as `OPEN` `DoseCalculationIssue` entries in `dose_verification_sandbox/data/issues.json`.

## Golden Calculation Dataset (Phase 16)

Because no real regimen reaches a non-BLOCKED state today, the 4-case golden dataset is synthetic
by necessity (explicitly permitted by the spec: "use synthetic fixtures for arithmetic tests").
All 4 cases (fixed dose, mg/kg/day, dose range, mg/kg/dose) pass exactly, labeled
`CALCULATION_VERIFIED`, never `CLINICALLY_APPROVED`. Distinct from and does not replace
`clinical_engine/golden_cases/` (the clinical Golden Dataset, still at 7 seed cases, all
`APPROVED_DATA_NOT_AVAILABLE`).

## Bug found and fixed during browser verification

Live UI testing (loading a real snapshot, selecting the Азитромицин/A63.8 regimen, calculating)
caught a real defect: when `calculation_status = BLOCKED`, the verdict builder (both `verify.py` and
its JS port in the HTML page) reported `max_dose = PASS` and `rounding = PASS` instead of
`NOT_AVAILABLE`, because `trace.max_dose_reason`/`rounding_status` are only set on the non-blocked
path and the verdict logic didn't check `calculation_status` first. Fixed in both places; regression
test added (`test_verify.py::test_blocked_arithmetic_never_reports_max_dose_or_rounding_as_pass`).
Full suite re-run green (45/45) after the fix, and the browser was re-verified live showing the
corrected `NOT_AVAILABLE` values.

## Exit gate checklist

| Gate | Status |
|---|---|
| MKB diagnosis selectable | ✔ (266 diagnoses from live snapshot) |
| Antibiotic selectable | ✔ |
| Regimen variant explicit | ✔ — all candidates listed, none merged |
| Source dose visible | ✔ — dose/unit/frequency/route/source_quote shown |
| Patient weight/age validated | ✔ — `UNSUPPORTED_INPUT` on missing/zero/negative |
| Calculation steps fully visible | ✔ — `TraceStep` list |
| Units checked | ✔ — `unit_consistency` verdict |
| Ranges remain ranges | ✔ (synthetic-verified; no real range data exists) |
| Maximum dose only if source-backed | ✔ — always `MAX_DOSE_NOT_AVAILABLE` on real data, never invented |
| Rounding explicit | ✔ — `NOT_APPLIED`, exact result always shown |
| Formulation conversion source-backed | ✔ — arithmetic implemented, `NOT_AVAILABLE` on real data (no source columns) |
| Owner can compare expected result | ✔ |
| Mismatch creates a QA issue | ✔ — 12 real issues filed |
| No medical value modified | ✔ — `test_invariants.py` confirms read-only + no clinical_engine import |
| No object approved | ✔ — `clinical_approval` hard-locked `NOT_APPROVED`; live-verified 0 `APPROVED` rows in `assembled_regimens.sqlite` |
| Clinical Engine remains disconnected | ✔ — sandbox never imports `clinical_engine`; reads only `assembled_regimens.sqlite` |
| Every result labeled QA / RESEARCH ONLY | ✔ — banner on every screen, every export, every doc |

## Final verdict

**B) DOSE VERIFICATION SANDBOX READY WITH BLOCKED DATA CASES**

The sandbox itself meets every exit gate. Every real regimen it was pointed at during the Phase 15
pilot legitimately blocked, because the upstream source schema (`assembled_regimens.sqlite`) cannot
currently express per-dose-vs-per-day, maximum dose, or formulation concentration. That is the
correct, honest outcome of a tool whose job is to refuse to guess — not a failure of the sandbox.
RC-030 tracks the upstream fix required before real (non-synthetic) `CALCULATION_VERIFIED` cases can
exist.

**P6 remains BLOCKED** — unaffected by this work; the sandbox does not touch approval state or the
Clinical Engine.
