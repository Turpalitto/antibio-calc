# RC-030 Commit B — Baseline Inventory

Generated: 2026-07-16. Authoritative HEAD: `7d45bcb196b5cd15aa4023034481de1c7026e3f0` (main).

## HEAD / status

- `git rev-parse HEAD` = `7d45bcb196b5cd15aa4023034481de1c7026e3f0`
- Branch: `main`
- Working tree: 4 modified tracked files, ~120 untracked paths (see classification below).

## Source database hashes (verified against evidence packet)

| File | SHA-256 | Matches evidence packet? |
|---|---|---|
| `assembled_regimens.sqlite` | `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9` | Yes — matches `source_hash` recorded in `evidence/regimen_5574_verified_evidence.json` |
| `backups/p5_6_baseline_20260715/normalized_regimens.sqlite` | `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237` | Yes — matches |

Both source databases are byte-identical to what the evidence packet claims to have queried. No source database was modified while preparing this commit.

## Approved-object / review state (queried live from `review_workbench_p56.sqlite`)

- `review_targets`: 9,153 rows
- `review_tasks.lifecycle_state`: 100% `PENDING` (9,153/9,153)
- `review_tasks.decision`: 100% empty string (no decision recorded)
- `review_decisions`: **0 rows**
- **Approved objects = 0** (verified at the data layer, not inferred from documentation)

## Clinical Engine isolation

`grep -rl "semantics_parser\|semantics_integration\|dose_verification_sandbox"` across all `*.py` outside `dose_verification_sandbox/` and `tests/dose_verification_sandbox/` returns exactly one file: `evidence/generate_regimen_5574_evidence.py` (an evidence-generation script that reads databases directly — it does not import RC-030 semantics/parser code, and nothing under `clinical_engine/` references RC-030 code). Clinical Engine remains disconnected.

## Test results

- `dose_verification_sandbox` targeted suite: `96 passed` (`pytest tests/dose_verification_sandbox -q`)
- Full canonical suite: `1455 passed, 1 xfailed, 0 failed` in 391.77s (`pytest -q`, 1456 collected)
- No unexpected failures.

## File classification (untracked + modified paths)

### A. RC-030 source code
- `dose_verification_sandbox/ambiguity_workflow.py`
- `dose_verification_sandbox/evidence_model.py`
- `dose_verification_sandbox/semantics_integration.py`
- `dose_verification_sandbox/semantics_models.py`
- `dose_verification_sandbox/semantics_parser.py`
- `dose_verification_sandbox/semantics_risk_audit.py`
- `dose_verification_sandbox/semantics_store.py`
- `dose_verification_sandbox/validation_status.py`
- `dose_verification_sandbox/calculator.py` (modified — sub-daily frequency block + per-single-dose max-dose fix)

### B. RC-030 tests
- `tests/dose_verification_sandbox/test_ambiguity_workflow.py`
- `tests/dose_verification_sandbox/test_semantics_parser.py`
- `tests/dose_verification_sandbox/test_sub_daily_frequency.py`
- `tests/dose_verification_sandbox/test_validation_status.py`

### C. RC-030 validation report
- `RC030_VALIDATION_BASELINE.md`, `RC030_DOSE_SEMANTICS_AUDIT.md`, `RC030_DOSE_SEMANTICS_REPORT.md`, `RC030_EVIDENCE_VALIDATION_REPORT.md`, `RC030_FALSE_POSITIVE_AUDIT.md`, `RC030_MAX_DOSE_VALIDATION.md`, `RC030_PRECISION_METRICS.md`, `RC030_RULE_CATALOG.md`, `RC030_SCHEMA_RESPONSIBILITY_DECISION.md`, `RC030_TARGETED_SOURCE_RECOVERY_REPORT.md`, `RC030_CORRECTED_FULL_CORPUS_REPORT.md`, `RC030_12CASE_REVALIDATION.md`, `DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md`, `DOSE_SEMANTICS_MODEL.md`, `DOSE_SEMANTICS_PARSER_SPEC.md`

### D. Evidence-integrity hardening
- `tests/dose_verification_sandbox/test_evidence_integrity.py`
- `tests/dose_verification_sandbox/test_false_positive_hardening.py`
- `evidence/generate_regimen_5574_evidence.py`
- `evidence/regimen_5574_verified_evidence.json`
- `REGIMEN_5574_VERIFICATION_REPORT.md`
- `RC031_EVIDENCE_INTEGRITY_HARDENING_REPORT.md`
- `RC031_RETRACTION_AUDIT.md`

### E. Corrected handoff documentation
- `AI_LOG.md`, `NEXT_TASK.md`, `PROJECT_STATE.md`, `ROOT_CAUSE_REGISTER.md` (all modified, tracked)

### F. Generated artifacts — exclude
- `dose_verification_sandbox/data/` (15 MB — corpus classification, snapshots, risk-audit output caches; regenerable)
- `CORPUS_MANIFEST.json` (produced by `clinical_engine/corpus/build_manifest.py`)
- `pilot_review_batch/` and `pilot_review_batch_v2/` (generated QA task-batch JSON, 424+424KB)
- `medical_dictionary/unknown_drugs.csv` (generated data-gap listing, not imported by any code)
- `REPOSITORY_UNTRACKED_INVENTORY.json`, `RECOVERY_TRACKED_FILES.txt` (leftover repo-recovery snapshots from an earlier, unrelated milestone)

### G. Unrelated change — exclude
- `P56_GOVERNANCE_HARDENING_CLOSURE_REPORT.md`, `P56_GOVERNANCE_HARDENING_FRESH_CLONE_REPORT.md`, `P56_GOVERNANCE_HARDENING_STAGED_AUDIT.md` (P5.6 governance milestone, not RC-030)
- `FORMULATION_DATA_GAP_REPORT.md` (formulation/unit data-gap tracking, not dose-semantics scope)

### H. Owner decision required
- `SESSION_HISTORY.md` (3,198 lines), `SESSION_SUMMARY.md` — raw session working notes; not a deliverable artifact and not requested by the RC-030 scope. Recommend excluding; owner should confirm before any future commit if retention is wanted.

No `git add` has been run. Nothing is staged.
