# Review DB Migration Reproducibility — Phase 7

Generated: 2026-07-15. All operations in this report ran against **disposable copies** under `tmp_migration_test/` (deleted after the test), never against the live `review_workbench_p56.sqlite`.

## 1. Schema-v1 fixture

Restored from the already-verified backup `backups/p5_6_governance_hardening_pre_migration_20260715/review_workbench_p56.sqlite` (itself SHA-256-verified byte-identical to the live pre-migration file when it was taken, per `P56_REVIEW_GOVERNANCE_MIGRATION_REPORT.md`).

## 2. Hash / row count of the fixture

- SHA-256: `2c39618b9dc7e2a83603baa76b0761c5cf9c8a36f566fa97e1d2715e9a5ae4ac`
- Schema version: **1**
- Total tasks: **9,153**
- By target type: ClinicalDataIssue 1265, ClinicalRegimen 1556, ConflictRecord 5615, CorpusExclusionDecision 58, GoldenCase 7, TherapeuticOption 652
- Non-PENDING tasks: **0**
- Unique `task_id` count: **9,153** (matches total — no duplicates)

## 3-4. Migration applied and schema validated

Opened via `ReviewStore(path)` (triggers the v1→v2 additive migration). Post-migration schema version: **2**.

## 5-6. Task IDs and target versions preserved

Compared `{task_id}` sets and `{task_id: (target_id, target_version)}` maps before and after migration: **exact match, both preserved** (9,153/9,153).

## 7. No decision invented

`review_decisions` row count post-migration: **0**.

## 8. Original task states preserved

State distribution before: `{'PENDING': 9153}`. After: `{'PENDING': 9153}`. **Identical.**

## 9. Idempotence

Re-opened the already-migrated (v2) copy a second time via `ReviewStore(path)`. Compared SHA-256 of the file before and after this second open: **byte-identical** — confirms the migration is a safe no-op when schema is already current, not a repeated/destructive operation.

## 10. Rollback / restore procedure test

Restored a fresh copy directly from the verified backup (`cp backups/.../review_workbench_p56.sqlite tmp_migration_test/copy2_for_rollback_test.sqlite`) and confirmed it opens at **schema version 1** with all **9,153** tasks intact — proving the backup is a genuine, usable rollback point independent of the migration having been run.

## Required invariants — all confirmed on the copy

| Invariant | Result |
|---|---|
| 9,153 tasks preserved | ✔ |
| 0 real decisions before and after | ✔ |
| 0 approved objects | ✔ |
| 30 pilot tasks remain PENDING | ✔ (all 9,153 tasks were PENDING before and after; the 30-task pilot subset is a subset of this population) |
| New tables begin empty | ✔ (`review_assignments`, `review_decisions`: 0 rows each) |
| Foreign-key/integrity checks pass | ✔ (`PRAGMA foreign_key_check` → `[]`; `PRAGMA integrity_check` → `ok`) |

## Cleanup

All test copies (`tmp_migration_test/copy1_v1.sqlite`, `tmp_migration_test/copy2_for_rollback_test.sqlite`) were deleted after verification. No clinical source database was mutated by this phase — only disposable copies were used.
