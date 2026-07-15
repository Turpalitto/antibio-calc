# Governance Hardening Closure — Phase 0 Baseline

Generated: 2026-07-15. Read-only capture before any closure-phase action.

## Repository state

- Root: `C:\ANTIBIO`
- Branch: `main`
- HEAD: `32096af5ac1c1227027ef4075863164f45251139`
- `git status --short`: 101 entries — 18 modified tracked files (review-workbench source/tests + governance docs), 83 untracked (60 pilot packets + legacy CSVs/session docs already classified in the recovery program, plus 20 new hardening-program files)
- `git diff --cached`: empty — nothing staged
- Full diff: 18 files changed, 940 insertions(+), 173 deletions(-)
- Tracked files: 453 (unchanged from the recovery commit)

## Modified tracked files (18)

`AI_LOG.md`, `CLINICAL_KNOWLEDGE_LIFECYCLE.md`, `NEXT_TASK.md`, `PROJECT_STATE.md`, `REGIMEN_APPROVAL_MODEL.md`, `REVIEW_WORKFLOW_RFC.md`, `ROOT_CAUSE_REGISTER.md`, `benchmark_review_workbench.py`, `clinical_engine/review_workbench/{api,models,service,storage}.py`, `clinical_engine/review_workbench/tests/{test_rc027_packet_provenance,test_real_review_artifact,test_review_api,test_review_workbench}.py`, `generate_pilot_review_batch.py`, `generate_pilot_review_batch_v2.py`.

## New untracked hardening files (candidates for a future commit, not yet decided)

`clinical_engine/review_workbench/reviewer_registry.py`, `clinical_engine/review_workbench/tests/{test_governance_hardening,test_pilot_safety_checks,test_reviewer_registry}.py`, plus 9 new governance-hardening documentation files (`P56_REVIEW_GOVERNANCE_HARDENING_BASELINE.md`, `P56_REVIEW_GOVERNANCE_HARDENING_REPORT.md`, `P56_REVIEW_GOVERNANCE_MIGRATION_REPORT.md`, `REVIEWER_IDENTITY_AND_ASSIGNMENT_POLICY.md`, `SECOND_REVIEW_BLINDING_SPEC.md`, `MEDICAL_QA_SIGNOFF_SPEC.md`, `REVIEW_CONSENSUS_STATE_MODEL.md`, `PHYSICIAN_PILOT_ACTIVATION_BASELINE.md`, `PHYSICIAN_REVIEW_PILOT_REPORT.md`, `POST_RECOVERY_EVIDENCE_CLASSIFICATION.md`, `GOLDEN_DATASET_APPROVED_ELIGIBILITY.md`). The rest of the 83 untracked entries are the pre-existing, already-classified recovery-program exclusions (pilot packet JSONs, legacy CSVs, session logs) — unchanged from `P56_PROPOSED_IGNORED_FILES.txt`.

## Review database facts

- `review_workbench_p56.sqlite` SHA-256: `22eee54c5a85dca7512357de97f50559b79fe06a1fcb8dfa280369142181eeb1` (post schema-v2-migration hash — differs from the pre-migration hash `2c39618b9d...` recorded in the prior session, as expected since the migration added columns/tables)
- Migration backup SHA-256 (`backups/p5_6_governance_hardening_pre_migration_20260715/review_workbench_p56.sqlite`): `2c39618b9dc7e2a83603baa76b0761c5cf9c8a36f566fa97e1d2715e9a5ae4ac` — matches the pre-migration live hash recorded when the backup was taken.
- Schema version: **2**
- Total tasks: **9,153**
- State distribution: **100% PENDING** (`{'PENDING': 9153}`)
- `review_assignments` rows: **0**
- `review_decisions` rows: **0**
- Approved objects (`PHYSICIAN_APPROVED`): **0**
- `PRAGMA integrity_check`: `ok`
- 30 pilot task states: **100% PENDING** (`{'PENDING': 30}`)
- Reviewer registry: an empty, stray `reviewer_registry.sqlite` (0 rows) was found at repo root — created as a side effect of some prior invocation using the API's default registry path rather than a test's isolated `tmp_path`. It contained **zero reviewers** (confirmed) and has been deleted as harmless build debris; it is `.gitignore`d (`*.sqlite`) regardless.
- Clinical Engine isolation: `grep -rln "review_workbench" clinical_engine/engine.py clinical_engine/pipeline.py clinical_engine/readers/ clinical_engine/api/` → **zero matches**, confirmed disconnected.

## Expected-baseline check

| Fact | Expected | Actual | Match |
|---|---|---|---|
| 9,153 tasks preserved | yes | 9,153 | ✔ |
| All 30 pilot tasks PENDING | yes | 30/30 PENDING | ✔ |
| No real reviewers | yes | 0 (after removing the empty stray file) | ✔ |
| No real assignments | yes | 0 | ✔ |
| No real decisions | yes | 0 | ✔ |
| Approved objects = 0 | yes | 0 | ✔ |

**All baseline facts hold. Proceeding to Phase 1.**
