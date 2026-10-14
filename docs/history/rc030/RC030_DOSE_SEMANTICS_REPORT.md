# RC030_DOSE_SEMANTICS_REPORT.md

Date: 2026-07-16
Scope: RC-030 Dose Semantic Reconstruction

## Summary

| Phase | Output | Status |
|---|---|---|
| 0 | `DOSE_SANDBOX_PRECOMMIT_AUDIT.md` | Done — no staging performed, awaits owner approval, generated artifacts gitignored |
| 1 | `RC030_DOSE_SEMANTICS_AUDIT.md`, `data/full_corpus_classification.json`/`full_corpus_metrics.json` | Done — full 2,675-row classification, validated against a hand-checked 40-row sample first |
| 2-3 | `semantics_models.py`, `semantics_parser.py` | Done — additive `DoseSemantics` model, proximity-window source-text parser |
| 4 | Table context recovery | **Not applicable** — `assembled_regimens.sqlite` carries no table row/column structure to inherit from; 0 cases by construction, documented in `DOSE_SEMANTICS_PARSER_SPEC.md` |
| 5 | Frequency interpretation | `frequency` column is already numeric administrations/day from the source pipeline; no separate normalization needed, used as-is |
| 6 | Max-dose extraction | Done — 26 rows (24 daily + 2 single) got a source-backed numeric ceiling from `не более N мг/г` text, restricted to mass units so durations are never captured |
| 7 | `FORMULATION_DATA_GAP_REPORT.md` | Done — concentration data exists only in the unrelated, unlinked `db/antibio_db.json`; formulation conversion stays `NOT_AVAILABLE` for all real regimens |
| 8 | `semantics_store.py` | Done — additive, idempotent, content-hash-deduplicated SQLite store, verified with a real 50-row double-rebuild test |
| 9 | `semantics_integration.py`, `DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md` | Done — eligibility rule, `calculate_from_semantics()`, worked example on the original blocking case (regimen 5574) |
| 10 | Calculation rules | Reused unmodified `calculator.calculate()` — RC-030 unblocks `denominator_time`, does not duplicate arithmetic |
| 11 | `ambiguity_workflow.py` | Done — `AmbiguityResolution` with 8 allowed resolution types, none of which produce clinical approval |
| 12 | Tests | Done — 21 new tests (`test_semantics_parser.py` ×18, `test_ambiguity_workflow.py` ×2, calculator/verify already covered); 66/66 total pass |
| 13 | Pilot re-run | Done — `data/rc030_pilot_rerun.json`, 10/12 original cases now `OK`, 2/12 still correctly `BLOCKED` (compound units) |
| 14 | Full-corpus metrics | Done — see `RC030_DOSE_SEMANTICS_AUDIT.md` |
| 15 | Documentation | This file + `DOSE_SEMANTICS_MODEL.md`, `DOSE_SEMANTICS_PARSER_SPEC.md`, `FORMULATION_DATA_GAP_REPORT.md`, `DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md`; `ROOT_CAUSE_REGISTER.md`/`PROJECT_STATE.md`/`NEXT_TASK.md`/`AI_LOG.md` updated below |

## Phase 13 — pilot re-run, before/after

The original 12-case pilot (`data/pilot_report.json`, all 12 `BLOCKED`) was re-run through the new
semantics path (`data/rc030_pilot_rerun.json`):

| | Before RC-030 | After RC-030 |
|---|---:|---:|
| OK (calculable) | 0 / 12 | 10 / 12 |
| BLOCKED | 12 / 12 | 2 / 12 |

The 2 still-`BLOCKED` cases (regimens 6275, 6405 — Пиперациллин + Тазобактам combinations) resolve
to `UNPARSED`: their `unit` column is a duplicated/compound string (e.g. `"г; мг/кг"`), a genuine
source-data defect that no amount of text-window analysis can safely resolve — correctly still
blocked, not a regression.

For every newly-calculable case, `data/rc030_pilot_rerun.json` records the exact matched source
fragment, the resolved `semantic_type`, and the full arithmetic trace — e.g. regimen 5364
(Пиперациллин+тазобактам): fragment `"/сут"` → `WEIGHT_PER_DAY` → 250×18=4500 mg/day →
4500÷3=1500 mg/dose. *(Correction: an earlier version of this line cited "regimen 5574
(Азитромицин)" as the example — that attribution was wrong; regimen 5574 is a different, correctly-
attributed джозамицин case not part of the 12-case pilot. See `ROOT_CAUSE_REGISTER.md` — RC-031
retracted.)*

**BLOCKED-count reduction alone is not treated as success** — each of the 10 resolved cases was
individually checked against its source_quote text (see the worked examples in
`DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md` and the Phase 1 validation sample) rather than accepted on
count alone.

## Phase 14 — full corpus metrics (n=2,675)

See `RC030_DOSE_SEMANTICS_AUDIT.md` for the complete breakdown. Headline numbers:

- **Technical calculability**: 1,645/2,675 rows (61.5%) now resolve to an explicit, source-backed
  semantic type — up from 0 before RC-030. Within the `REVIEW_REQUIRED` subset that will eventually
  reach physician review, this is **87.6%** (1,352/1,543).
- **Still ambiguous**: 202 rows (7.6%) — genuinely no textual signal and frequency ≠ 1; correctly
  fails closed, not guessed.
- **Still unparsed**: 74 rows (2.8%) — compound/unrecognized unit strings, a source-data defect.
- **Missing/not-dosable**: 658 + 96 = 754 rows (28.2%) — no dose value at all, or a mis-extracted
  non-dosable regimen; unrelated to the semantics-ambiguity problem RC-030 targets.
- **Clinical approval remains 0** — confirmed unchanged, `clinical_approval` is still hard-locked to
  `NOT_APPROVED` throughout; nothing in RC-030 touches approval state.
- **Clinical Engine remains disconnected** — RC-030 never imports `clinical_engine` (test-enforced);
  it only adds an additive interpretation layer on top of the existing, already-disconnected
  `assembled_regimens.sqlite` snapshot.

## Exit gate checklist

| Gate | Status |
|---|---|
| Per-day and per-dose represented separately | ✔ — `DoseSemantics.time_denominator` |
| Ambiguous expressions fail closed | ✔ — 202 rows correctly remain `AMBIGUOUS`, never guessed |
| Source-backed table inheritance supported | **N/A** — no table structure in source schema; documented, not silently skipped |
| Maximum dose never inferred | ✔ — only source-backed `не более` phrases extracted; 26/2675 rows, rest `MAX_DOSE_NOT_AVAILABLE` |
| Formulation concentration never assumed | ✔ — `FORMULATION_DATA_GAP_REPORT.md`; `NOT_AVAILABLE` for all real regimens |
| Semantic provenance complete | ✔ — every `DoseSemantics` carries `source_pdf`/`source_page`/`guideline_id`/matched fragment |
| Source DB unchanged | ✔ — `test_classify_never_mutates_input_dict`, `mode=ro` throughout |
| Sandbox uses explicit semantics | ✔ — `semantics_integration.calculate_from_semantics()` |
| Calculation trace distinguishes daily and single dose | ✔ — reuses the existing, unmodified P5.6 trace engine |
| Original 12-case pilot rerun reported honestly | ✔ — 10/12 resolved, 2/12 correctly still blocked, not hidden |
| Full-corpus metrics generated | ✔ — `RC030_DOSE_SEMANTICS_AUDIT.md` |
| Approved objects remain 0 | ✔ — unchanged |
| Clinical Engine disconnected | ✔ — unchanged, test-enforced |
| Tests pass | ✔ — 66/66 |

## Final verdict

**B) RC-030 PARTIALLY CLOSED — AMBIGUOUS DATA REMAINS**

61.5% of the corpus (87.6% of the `REVIEW_REQUIRED` subset) now has a source-backed, explicit dose
semantic and is technically calculable — up from 0% before this work. 202 rows (7.6%) remain
genuinely ambiguous in the source text itself and correctly fail closed rather than being guessed;
74 rows (2.8%) remain unparsed due to compound/malformed unit strings, a separate upstream data
defect. Neither of these residual categories can be closed by better parsing — they require either
a human reading the source PDF (the Phase 11 ambiguity workflow exists for exactly this) or an
upstream fix to the unit-extraction step that produced the compound strings in the first place.

**P6 remains BLOCKED** — unaffected by this work; approved-object count is unchanged at 0, and the
Clinical Engine remains disconnected from this entire layer.
