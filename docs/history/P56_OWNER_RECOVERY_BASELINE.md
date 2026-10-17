# P5.6 Owner Recovery — Phase 0: Worktree & Repository Authority Audit

Generated: 2026-07-15. Read-only audit. No files moved, merged, staged, or committed.

## 1. Working directory / repository root

- Current working directory: `C:\ANTIBIO`
- `git rev-parse --show-toplevel`: `C:/ANTIBIO`
- These are the same path. There is no ambiguity between "cwd" and "repo root" for the main checkout.

## 2. All Git worktrees

| Path | Branch | HEAD | Status |
|---|---|---|---|
| `C:/ANTIBIO` | `main` | `b806c21` | ahead of `origin/main` by 1 commit; **9 modified tracked files + 500 untracked non-ignored files** |
| `C:/ANTIBIO/.claude/worktrees/post-rebuilder-continuation-de6374` | `claude/post-rebuilder-continuation-de6374` | `b806c21` | clean — `git status --short` empty |
| `C:/ANTIBIO/.claude/worktrees/project-onboarding-fd0f0d` | `claude/project-onboarding-fd0f0d` | `b806c21` | clean — `git status --short` empty |

All three worktrees share the same HEAD commit (`b806c21`). The two secondary worktrees contain **only the 19 files already tracked in Git** (`antibiotic_calc.html`, `.gitignore`, `build_html.ps1`, `db/`, `server.js`, `antibiotic_calc.html.template`, `.claude/`) and have zero uncommitted changes. They are not divergent — they are simply unused checkouts at the same commit as `main`.

## 3. Files unique to each worktree

- **`C:/ANTIBIO` (main checkout) has ~500 untracked files that do not exist in either secondary worktree**: the entire `src/`, `clinical_engine/`, `medical_dictionary/`, `medical_normalizer/`, `docs/`, `config/`, `pilot_review_batch/`, `pilot_review_batch_v2/` trees, ~130 governance/RFC/report Markdown files at repo root, `pyproject.toml`, `uv.lock`, generated SQLite/PDF artifacts (already gitignored), and 9 modified tracked files (`.gitignore`, `antibiotic_calc.html`, `antibiotic_calc.html.template`, `build_html.ps1`, `db/antibio_db.json`, `db/build_db.ps1`, `db/diseases/*.json`, `db/index.json`).
- **The two secondary worktrees have no files unique to them.** They are strict subsets of the main checkout's tracked set, at the identical commit.

## 4. Conflicting edits / files newer in one location

None found. No file exists in a secondary worktree with content different from the same path in `main`, because the secondary worktrees only contain the 19 tracked files, unmodified, at the same commit `main` currently has checked out. There is nothing to reconcile — no merge, no diff resolution needed.

## 5. Cross-worktree write risk

- No evidence of cross-worktree writes: `git worktree list` shows no locked/prunable worktrees, and `git status` in each secondary worktree is clean.
- All absolute-path risk is contained to `C:/ANTIBIO` itself, which is the intended location for this recovery program.

## 6. Authoritative checkout selection

**Selected authoritative source tree: `C:/ANTIBIO` (the `main` branch working tree).**

Justification:
- It is the only location holding the ~500 untracked files that represent the actual engineering work (Clinical Engine, medical normalizer, dictionary, tests, governance docs, dependency manifests).
- The two secondary worktrees hold no unique or divergent state — they are safe to leave untouched pending Phase 14 (Worktree Consolidation), not because they're at risk of loss, but because there is nothing in them to lose.
- `main` is 1 commit ahead of `origin/main`; that commit (`b806c21`) is already pushed to no remote branch conflict — recovery work proceeds on top of it.

## 7. Rollback snapshot procedure

Before any staging or commit action (Phase 10+), the following reversible checkpoint is available:

1. Nothing has been staged yet — `git status` still shows only the pre-existing 9 modified tracked files and 500 untracked files exactly as of session start.
2. To fully roll back this audit at any point: no rollback is needed, since Phase 0/1 perform no writes to tracked state (only new report files are created at repo root, which themselves remain untracked until an explicit owner-approved `git add`).
3. If an owner wants to discard only the new report/audit files created by this program, they are all untracked and can be removed individually (never via `git clean -f` without listing paths, per standing safety rules).
4. The current commit `b806c21` remains the rollback point for any tracked-file regression: `git checkout -- <path>` (single file) or, if ever needed and owner-approved, `git reset --hard b806c21` (destructive; requires explicit owner approval; not performed here).

## Exit gate

**PASSED** — one authoritative source tree (`C:/ANTIBIO`, `main`) is explicitly selected and justified above. Proceeding to Phase 1 (immutable recovery snapshot).
