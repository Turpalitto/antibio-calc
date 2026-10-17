# RC-030 Commit B — Pre-Staging Audit

Generated: 2026-07-16. Scanned against the exact allowlist below (not `git add .`, no wildcard staging).

## Allowlist scanned (39 paths — corrected count; original draft miscounted as 35)

```
AI_LOG.md
NEXT_TASK.md
PROJECT_STATE.md
ROOT_CAUSE_REGISTER.md
dose_verification_sandbox/ambiguity_workflow.py
dose_verification_sandbox/calculator.py
dose_verification_sandbox/evidence_model.py
dose_verification_sandbox/semantics_integration.py
dose_verification_sandbox/semantics_models.py
dose_verification_sandbox/semantics_parser.py
dose_verification_sandbox/semantics_risk_audit.py
dose_verification_sandbox/semantics_store.py
dose_verification_sandbox/validation_status.py
tests/dose_verification_sandbox/test_ambiguity_workflow.py
tests/dose_verification_sandbox/test_semantics_parser.py
tests/dose_verification_sandbox/test_sub_daily_frequency.py
tests/dose_verification_sandbox/test_validation_status.py
tests/dose_verification_sandbox/test_evidence_integrity.py
tests/dose_verification_sandbox/test_false_positive_hardening.py
evidence/generate_regimen_5574_evidence.py
evidence/regimen_5574_verified_evidence.json
REGIMEN_5574_VERIFICATION_REPORT.md
RC031_EVIDENCE_INTEGRITY_HARDENING_REPORT.md
RC031_RETRACTION_AUDIT.md
RC030_VALIDATION_BASELINE.md
RC030_DOSE_SEMANTICS_AUDIT.md
RC030_DOSE_SEMANTICS_REPORT.md
RC030_EVIDENCE_VALIDATION_REPORT.md
RC030_FALSE_POSITIVE_AUDIT.md
RC030_MAX_DOSE_VALIDATION.md
RC030_PRECISION_METRICS.md
RC030_RULE_CATALOG.md
RC030_SCHEMA_RESPONSIBILITY_DECISION.md
RC030_TARGETED_SOURCE_RECOVERY_REPORT.md
RC030_CORRECTED_FULL_CORPUS_REPORT.md
RC030_12CASE_REVALIDATION.md
DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md
DOSE_SEMANTICS_MODEL.md
DOSE_SEMANTICS_PARSER_SPEC.md
```

## Results

| Scan | Result |
|---|---|
| Secret scan (api_key/secret/password/token/bearer patterns) | **0 matches** |
| Personal-path scan (`C:\Users\<name>`, `/home/`, `/Users/`) | **0 matches** |
| `C:\ANTIBIO` / repo-absolute-path leakage | **0 matches** |
| DB/PDF/model-weight/cache scan (`*.sqlite*`, `*.db`, `*.pdf`, `*.pt`, `*.onnx`, `*.bin`) | **0 matches** |
| Large-file scan (>500 KB) | **0 matches** |
| Generated-artifact scan | `dose_verification_sandbox/data/`, `CORPUS_MANIFEST.json`, `pilot_review_batch/`, `pilot_review_batch_v2/`, `medical_dictionary/unknown_drugs.csv` are **not on the allowlist** (correctly excluded — see `RC030_COMMIT_B_BASELINE.md` category F) |
| Synthetic-data leakage | `evidence/regimen_5574_verified_evidence.json` content cross-checked against live DB hashes (see below) — real data, not synthetic |
| Clinical source-value diff audit | `ROOT_CAUSE_REGISTER.md`/`NEXT_TASK.md` diffs read in full: RC-031 correctly marked RETRACTED with hash-backed drug name (джозамицин, not Азитромицин); RC-030 entry states verdict B (BLOCKED) consistently; no drug/dose/frequency value asserted in prose diverges from the machine-generated evidence packet |

## Evidence packet cross-check (repeated independently in this audit)

- `assembled_regimens.sqlite` live SHA-256: `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9` — matches packet.
- `backups/p5_6_baseline_20260715/normalized_regimens.sqlite` live SHA-256: `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237` — matches packet.
- Both independently confirm `антибиотик=джозамицин` for regimen 5574; no Азитромицин reference remains in any allowlisted file.

## Fail-closed re-confirmation (independent of `RC030_FAIL_CLOSED_IMPLEMENTATION_AUDIT.md`)

- `dose_verification_sandbox/validation_status.py:38` — `TYPES_MEETING_PRECISION_THRESHOLD` is empty → all `calculation_eligibility` resolves to `BLOCKED`.
- `review_workbench_p56.sqlite` — `review_decisions` = 0 rows, all 9,153 tasks `PENDING` (queried live at 2026-07-16, same result as baseline).
- No RC-030 file among the 35 allowlisted paths imports from or is imported by `clinical_engine/`.

## Test re-run against the allowlist's own suites

- `pytest tests/dose_verification_sandbox -q` → **96 passed**
- `pytest -q` (full canonical, 1456 collected) → **1455 passed, 1 xfailed, 0 failed**

## Stop point

Staging has **not** been performed. No `git add` command has been run against this allowlist.
