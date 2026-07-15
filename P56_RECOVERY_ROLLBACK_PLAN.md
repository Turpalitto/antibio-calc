# P5.6 Phase 1 — Recovery Rollback Plan

Generated: 2026-07-15. No tracked-state changes have been made by this program yet.

## Current immutable reference point

- Branch: `main`
- HEAD commit: `b806c21` ("fix: unit dosing bugs, expand DB to 72 nosologies/40 drugs, correct 39 misattributed KR numbers")
- Remote: `origin` = `https://github.com/Turpalitto/antibio-calc.git`; local `main` is 1 commit ahead of `origin/main`
- `git diff --cached` is empty — nothing is currently staged
- Raw snapshots captured verbatim in `tmp/git_status.txt`, `tmp/git_diff.txt`, `tmp/git_diff_cached.txt`, `tmp/git_ls_files.txt`, `tmp/git_worktree_list.txt`, `tmp/git_branch.txt`, `tmp/git_remotes.txt` (local working files, not part of the tracked-file manifest)

## What is hashed (Phase 1 integrity baseline)

`P56_PRE_RECOVERY_FILE_MANIFEST.json` and `P56_PRE_RECOVERY_HASHES.txt` contain SHA-256 hashes for **323 files** (6.4 MB) spanning source code, tests, migrations, configuration templates, and scripts (categories A/B/C/D/E/F/G/H from the Phase 3 classification). These hashes are the rollback reference: after any staging/commit action, re-running the same hash pass over the same path list must reproduce identical digests for every file not intentionally changed.

## What is excluded from the hash manifest (backed up separately, never staged)

- Runtime SQLite databases (`kb_p44.db`, `assembled_regimens.sqlite`, etc.) — already gitignored (`*.db`, `*.sqlite`) and already snapshotted at `backups/p5_6_baseline_20260715/` (verified byte-identical to live files for `kb_p44.db` and `assembled_regimens.sqlite`).
- PDF source corpus (7 files) — gitignored (`*.pdf`).
- 128 report/RFC/analysis Markdown files (category S) and 67 generated JSON artifacts (category J, mostly `pilot_review_batch/` and `pilot_review_batch_v2/` packets) — these are process-history documents, not required for a fresh clone to function; their commit/exclusion decision is deferred to Phase 8/9 (owner review), not to this rollback plan.
- `.claude/launch.json` (category T) — local dev-preview config, owner decision required before it can be tracked.

## Rollback procedure if a later phase needs to be undone

1. **Before staging (Phases 0-9):** no rollback needed — no `git add` has occurred. Any newly-created report file (`P56_*.md`, `*.json`, `*.csv`, `*.txt`) is untracked and can be deleted individually if the owner wants a clean slate; this does not touch git history.
2. **After staging but before commit (Phase 10):** `git restore --staged <path>` reverses staging without touching the working tree.
3. **After the recovery commit (Phase 12):** the pre-commit state is fully recoverable via `git reset --soft b806c21` (keeps working tree, unstages the recovery commit) — this is destructive to the *commit*, not to file contents, and per the standing safety protocol requires explicit owner approval before execution.
4. **Content-level verification at any point:** re-run the SHA-256 pass against `P56_PRE_RECOVERY_HASHES.txt` for the 323-file source/test/doc/config baseline; any mismatch on a file not deliberately edited flags accidental modification.
5. **Runtime databases:** restore from `backups/p5_6_baseline_20260715/` (already verified identical to live state); this path is outside Git entirely, so no git operation can affect it.

No secret values are included in any Phase 1 artifact.
