# DOSE_VERIFICATION_SANDBOX_AUDIT.md

Status: PHASE 0 — pre-implementation audit
Scope: P5.6 Dose Calculation Verification Sandbox (QA / RESEARCH ONLY)
Date: 2026-07-15
Method: static code search + live, read-only inspection of `kb_p44.db`, `kb_final.db`, `assembled_regimens.sqlite`, `review_workbench_p56.sqlite`, `db/antibio_db.json`. No files were modified to produce this report.

This document is the required Phase 0 gate. It records what exists, what is reusable, what is frozen, what is missing, and exactly which files the sandbox is proposed to touch. No Clinical Engine redesign is proposed here.

---

## 0. Correction to first-pass exploration

An initial exploratory pass reported `ClinicalRegimen = 1556` and `TherapeuticOption = 652` as rows in `kb_p44.db`'s `objects` table. **Live re-query does not confirm this.** As of this audit:

```
kb_p44.db  objects.type counts: Contraindication=841, Diagnosis=431, Dose=24705,
                                  Evidence=2190, Medication=2788, Recommendation=381
```

No `ClinicalRegimen` or `TherapeuticOption` rows exist in `kb_p44.db` or `kb_final.db`. Those object types are produced and persisted **only** by `clinical_engine/regimen/store.py`, which — per its own module docstring — "Writes a NEW sqlite file (`assembled_regimens.sqlite`) — never touches kb_p44.db or [normalized_regimens]". Live inspection of `assembled_regimens.sqlite` confirms:

```
assembled_regimens table: 2,675 rows
statuses observed: REJECTED, REVIEW_REQUIRED  (no APPROVED rows)
rows with numeric dose + non-empty unit: 1,870
rows with unit == 'mg/kg' and non-null frequency: 589
rows with status != REJECTED: 1,543
```

**This is the correct and only ground truth for the sandbox's regimen data.** The rest of this document is written against verified live state, not the earlier report.

---

## 1. Diagnosis / MKB (ICD-10) lookup

- Code: `clinical_engine/readers/diagnosis_reader.py` — `JsonDiagnosisProvider`, reads `clinical_engine/resources/diagnosis_index.json`.
- Data: `diagnosis_index.json` is `meta.status = "AUTO_GENERATED_DRAFT"`, mechanically extracted, **not clinically curated**: 895 entries, 101 conflicting mappings, 127 duplicate names, 2 missing ICD-10 codes.
- `assembled_regimens.sqlite` carries its own `diagnosis` (free text, source language) and `icd_mkb` columns directly on each regimen row — this is denser and simpler than joining through `diagnosis_index.json`, and is what the sandbox should use as the primary diagnosis selector source, since every regimen row is self-contained.
- Reuse: use `icd_mkb` + `diagnosis` columns from `assembled_regimens` directly. Do not depend on `diagnosis_index.json` for the sandbox — it is unrelated to this table and would introduce an extra unverified join.

## 2. Antibiotic selection

- `assembled_regimens.antibiotic` is a free-text column (source-language drug name), already scoped per regimen row — no separate antibiotic master table is joined at assembly time.
- The Clinical Engine's own antibiotic-selection pipeline (`clinical_engine/stages/regimen_load.py`) reads `normalized_regimens.sqlite`, a **third, different** data source, and is mid-pipeline (Stage 2 of 7), not a place to select from directly.
- Reuse: for the sandbox, "select antibiotic" = filter `assembled_regimens` rows by `diagnosis`/`icd_mkb`, then list distinct `antibiotic` values among matching rows. No new antibiotic entity is needed.

## 3. Regimen model — ClinicalRegimen / TherapeuticOption

- Design: `CLINICAL_REGIMEN_MODEL.md` (PROPOSED), `THERAPEUTIC_OPTION_RULES.md` (ADOPTED) — TherapeuticOption never carries a dose; only ClinicalRegimen does.
- Implementation: `clinical_engine/regimen/clinical_regimen.py`, `assembly_engine.py`, `store.py`, `approval_workflow.py`, `validator.py`, `conflict_detector.py`.
- Live data: `assembled_regimens.sqlite`, table `assembled_regimens`, 2,675 rows, schema includes `regimen_id, version, status, diagnosis, icd_mkb, age_group, pregnancy, renal_adjustment, therapy_line, antibiotic, dose, unit, frequency, duration_recommended, route, guideline_id, evidence_level, contraindications, review_status, approved_by, approved_at, validation_verdict, confidence, source_pdf, source_page, source_quote, field_provenance, needs_review_reasons, snapshot_version, assembly_ruleset_version, created_at`.
- No `TherapeuticOption` rows are separately materialized in this table — this table appears to only hold ClinicalRegimen-shaped rows. The sandbox therefore only has ClinicalRegimen data to work with; TherapeuticOption entity comparison (Phase 3's "distinguish ClinicalRegimen from TherapeuticOption") reduces to: **every row in this table is a ClinicalRegimen candidate; there is currently no TherapeuticOption dataset to select from.** This must be stated on-screen, not silently ignored.
- Reuse: `assembled_regimens.sqlite` is the single, self-sufficient, read-only data source for the sandbox. It already has provenance (`source_pdf`, `source_page`, `source_quote`), approval state (`status`, `review_status`, `approved_by`, `approved_at`), and a validation verdict (`validation_verdict`) — everything Phase 3 asks the selector to display.

## 4. Dose expression model — what the source data actually looks like

Unlike the spec's illustrative "50 mg/kg/day" free-text example, `assembled_regimens` already stores a **partially structured** dose: `dose` (REAL), `unit` (TEXT), `frequency` (REAL, times/day), `duration_recommended` (REAL, days). This is good — no free-text dose parsing is needed for the common case — but it has a critical, verified gap:

- **There is no field for "per single dose" vs. "per day".** The schema does not distinguish `mg/kg/dose` from `mg/kg/day`. Example live row: `regimen_id=5574, dose=50, unit='mg/kg', frequency=2.0` — is 50 mg/kg the daily total or the single-administration amount? The column set cannot answer this. `source_quote` sometimes contains the original sentence (in source language) that could disambiguate, but that requires the human reviewer to read it — the sandbox must **not** guess.
- `unit` values observed in live data: `'', 'mg', 'mg/kg', 'g', 'капли' (drops), 'IU', '%', 'мг/сут' (mg/day — day IS specified here), 'г; мг/кг' (compound/garbled — two units concatenated), 'мл/кг/сут; мл/кг/сут' (duplicated), 'капель', 'мл'`.
  - Atomic, unambiguous units found: `mg`, `g`, `IU`, `%`, `мг/сут` (explicit per-day), `мл` (already volume, no conversion needed).
  - `mg/kg` alone: weight-scaled but period-ambiguous (see above) — **must be flagged, not computed silently.**
  - Compound/duplicated strings like `'г; мг/кг'`, `'мл/кг/сут; мл/кг/сут'`: not machine-parseable at all — `parser_status = UNPARSED`.
- No `numeric_max` / range column exists — every dose is a single point value in this table. Range handling (Phase 6) has no real data to exercise; it will only be exercisable via synthetic fixtures, which is acceptable per the spec ("use synthetic fixtures for arithmetic tests").
- No `max_single_dose` / `max_daily_dose` columns exist at all. Any "maximum dose" phase (Phase 7) has **zero source-backed data** in this table — every real case must resolve to `MAX_DOSE_NOT_AVAILABLE`, never a computed cap.
- Reuse: `medical_normalizer/drug_parser.py`'s `DoseNormalizer`/`UnitNormalizer` are usable as a reference implementation for tokenizing unit strings, but the sandbox needs its own thin adapter, because `assembled_regimens` dose/unit are already split into columns (no free-text re-parsing of the numeric part needed) — only the *unit semantics* (denominator_time, compound-unit detection) need parsing logic.

## 5. Dose calculator

- `clinical_engine/stages/dose_calculation.py` (Stage 6): pediatric branch requires `pediatric_dosing` sub-object which is absent for all 40 drugs in `db/index.json` — dormant on real data, not reusable as-is for the sandbox (it reads a different schema entirely, not `assembled_regimens`).
- `antibiotic_calc.html` `computeDose()` (JS, line ~761): working reference implementation (dailyMg = weight × perKg; cap at maxDaily if present; singleMg = dailyMg / freq) — useful as a pattern reference for the trace engine's arithmetic, but it operates on `db/antibio_db.json`'s hand-curated 28-drug dataset, an entirely different (and disconnected) data source from `assembled_regimens.sqlite`.
- Reuse: neither existing calculator can be called directly against `assembled_regimens.sqlite` — both assume a differently-shaped input. The sandbox must implement its own small, deterministic calculation module against the verified real schema (§4 above), following the same "explicit trace, no inference" pattern as `computeDose()`.

## 6. Frequency / duration parsing

- `assembled_regimens.frequency` and `.duration_recommended` are already numeric (times/day, days) — no free-text frequency/duration parsing is required for this table. `medical_normalizer/frequency_parser.py` / `duration_parser.py` remain available as reference for any future free-text ingestion but are out of scope for the sandbox's direct inputs.

## 7. Renal adjustment

- `assembled_regimens.renal_adjustment` is an **integer flag** (0/1), not structured dosing rules — it indicates only whether renal adjustment is relevant, not by how much. No numeric renal-adjustment logic exists anywhere in the codebase (confirmed in `clinical_engine/stages/dose_adjustment.py`, which treats renal text as an unparsed WARNING sentinel, never a numeric adjustment).
- Sandbox behavior: if `renal_function` input is supplied and `renal_adjustment == 1` on the selected regimen, the sandbox must show `renal_function` as a recorded input with calculation_status noting no source-backed adjustment formula exists — never adjust the dose number.

## 8. Weight- / age-based calculation

- `assembled_regimens.age_group` is a coarse bucket (`adult`, `child`, ...), not a numeric age range — matches the spec's own model (`age_value`/`age_unit` as free patient input, compared against the regimen's declared scope for a match/mismatch flag, not a hard numeric filter).
- No `weight_min_kg`/`weight_max_kg` columns exist on `assembled_regimens` (unlike `db/schema.json`'s separate app schema, which does have them). Weight-band under/over-range warnings (spec Phase 3, "weight scope") therefore have no source data to check against for this table — must show `NOT_AVAILABLE`, not silently pass.

## 9. Rounding

- No governed rounding policy exists anywhere in the repository. `antibiotic_calc.html` only does UI-level display rounding (`Math.round`, `.toFixed(1)`, half-tablet). Confirmed: no adopted `DOSE_ROUNDING_POLICY.md` exists yet — the sandbox creates the first one, and it is a documentation-only policy: `NO_ROUNDING` mode, exact result always shown, matching spec Phase 8 exactly.

## 10. Dosage-form / concentration conversion

- No concentration/formulation data exists in `assembled_regimens.sqlite` (no `concentration_mg_per_ml`, no formulation table join). `db/antibio_db.json` (used by `antibiotic_calc.html`) has this, but is a disconnected, hand-curated dataset unrelated to `assembled_regimens`. Consequence for the sandbox: formulation conversion (Phase 9) has **no real data to exercise** against `assembled_regimens` rows — every real case resolves to "show dose in mg/original unit only", exactly as the spec instructs when formulation is absent. Synthetic fixtures will exercise the conversion arithmetic itself.

## 11. Existing calculator UI / API

- `antibiotic_calc.html` + `server.js`: complete, working, but a static file server with **no API endpoints** and **zero automated tests**, operating on an entirely separate dataset (`db/antibio_db.json`). Not reusable as infrastructure for the sandbox beyond serving as a UI-pattern reference (single static HTML file, offline-capable, no backend writes) — which is in fact the safest architecture to copy for isolation (Phase 1 requirement: no production endpoint).

## 12. Golden Dataset

- `clinical_engine/golden_cases/`: schema + runner exist, only 7 seed cases, all `APPROVED_DATA_NOT_AVAILABLE` (system-wide approved-object count = 0, independently reconfirmed live: `review_workbench_p56.sqlite.review_tasks` has 9,153 rows, all with empty `consensus_result`/`qa_verdict`). This is the **clinical** Golden Dataset — the spec's Phase 16 explicitly requires a **separate arithmetic** Golden Dataset (`CALCULATION_VERIFIED`, not `CLINICALLY_APPROVED`) which does not yet exist anywhere and will be created fresh under the sandbox's own directory.

## 13. Database schema (live-verified)

| File | Tables | Verified counts |
|---|---|---|
| `kb_p44.db` | objects, provenance, reviews, conflicts | Contraindication=841, Diagnosis=431, Dose=24705, Evidence=2190, Medication=2788, Recommendation=381 (no ClinicalRegimen/TherapeuticOption rows) |
| `kb_final.db` | same schema | Contraindication=1, Dose=275, Evidence=1, Medication=16 (much smaller subset) |
| `assembled_regimens.sqlite` | assembled_regimens | 2,675 rows; statuses {REJECTED, REVIEW_REQUIRED}; 1,870 rows with dose+unit; 589 rows with unit='mg/kg' and frequency set |
| `review_workbench_p56.sqlite` | review_targets, review_tasks, ... | 9,153 review_tasks, 0 with a non-empty consensus_result or qa_verdict |

## 14. Approval / review state model

- Confirmed live: **0 approved clinical objects**, matches `PROJECT_STATE.md`. `assembled_regimens.status` only ever takes values `REJECTED` or `REVIEW_REQUIRED` in current data — **no `APPROVED` value exists yet in this table at all.** Every regimen the sandbox can show is therefore, at best, `REVIEW_REQUIRED` — this must be visually unmissable on every screen per Phase 1/13.

## 15. Clinical Engine connection status

- Confirmed: `clinical_engine/regimen/store.py` writes only to `assembled_regimens.sqlite`; the live Clinical Decision Engine (`clinical_engine/stages/*`) reads `normalized_regimens.sqlite`, a third and different store. The two are not wired together (RC-019, open). The sandbox reading `assembled_regimens.sqlite` is therefore **not** reading "what the Clinical Engine would return" — it is reading the shadow Regimen Assembly Engine's output. This distinction must be stated in the UI and docs so the owner never mistakes sandbox output for engine output.

---

## What already exists vs. what is missing

**Reusable as-is:**
- `assembled_regimens.sqlite` — complete, self-contained, read-only source of regimen rows with provenance and approval state. No further extraction needed.
- Static single-file HTML UI pattern (`antibiotic_calc.html`) as an architecture reference for isolation (Phase 1).

**Missing, must be built new for the sandbox:**
- Unit-semantics parser distinguishing per-dose vs per-day, detecting compound/unparseable unit strings (§4).
- Deterministic calculation trace engine against the verified real schema (§5).
- Rounding policy document (first one in the repo) (§9).
- Arithmetic Golden Dataset, separate from the clinical one (§12).
- Local, append-only QA issue log (Phase 12) — does not exist.
- Owner-comparison UI (Phase 11) — does not exist.

**Frozen / do-not-touch:**
- `medical_normalizer/*` (parsers) — read-only reference, not modified.
- `clinical_engine/stages/*`, `clinical_engine/regimen/*` — read-only reference, not modified; sandbox never calls into these modules to avoid any chance of triggering writes.
- `kb_p44.db`, `kb_final.db`, `normalized_regimens.sqlite`, `review_workbench_p56.sqlite`, `assembled_regimens.sqlite` — opened strictly read-only (`sqlite3.connect(..., uri=True)` with `mode=ro`) by the export step; never written to.

## Exact files proposed for change

All new, isolated under a new `dose_verification_sandbox/` directory plus a `tests/dose_verification_sandbox/` test directory and a handful of root-level docs required by Phase 17. **No existing file is modified**, except the three MD-handoff-protocol status files (`PROJECT_STATE.md`, `NEXT_TASK.md`, `AI_LOG.md`) at the end of the task, per repository convention.

```
dose_verification_sandbox/
  __init__.py
  models.py            (Phase 2, 4, 5, 10, 12)
  snapshot.py           (Phase 3 — read-only export from assembled_regimens.sqlite)
  parser.py             (Phase 4 — unit/denominator parser)
  calculator.py          (Phase 5-9 — trace engine)
  verify.py             (Phase 10-11 — verdicts + owner comparison)
  issues.py             (Phase 12 — local append-only issue log)
  golden.py              (Phase 16 — golden calculation dataset runner)
  data/                 (generated snapshot + issue log + golden dataset JSON — gitignored working data, sample committed)
  ui/dose_verification_sandbox.html   (Phase 13 — static, offline, read-only viewer)

tests/dose_verification_sandbox/
  test_parser.py
  test_calculator.py     (Phase 14 test matrix)
  test_golden.py

DOSE_VERIFICATION_SANDBOX_SPEC.md
DOSE_CALCULATION_TRACE_SPEC.md
DOSE_ROUNDING_POLICY.md
DOSE_VERIFICATION_USER_GUIDE.md
DOSE_VERIFICATION_SANDBOX_REPORT.md
```

## Phase 0 conclusion

The sandbox can be built entirely against `assembled_regimens.sqlite` in strict read-only mode, without touching the Clinical Engine, `kb_p44.db`, or any approval workflow code. The most important finding is a genuine data-model gap: **the source schema cannot currently distinguish per-dose from per-day for `mg/kg`-unit regimens**, and has no max-dose or formulation-concentration columns at all. This is not a sandbox bug to work around — it is the correct QA finding the sandbox exists to surface, and it will produce real `DoseCalculationIssue` / `BLOCKED` records against real data from day one (Phase 15).

Proceeding to Phase 1 (isolation) and Phase 2 (input model) implementation.
