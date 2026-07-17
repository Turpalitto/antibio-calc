# RC-030 Test Portability — Post-Commit Report

Commit: `3948186` (`test(rc030): make database invariants portable in bare clones`), direct child of `dd8b3ad`, on `main`. New commit — no amend, no squash, no rebase, no push.

## Commit record

- Full hash: `394818675b0ed199e03cae1d89e38a488f5102ce`
- Parent: `dd8b3adad1ca60d3119ac7b48e6e50dbe364d328`
- Branch: `main`
- Author: Ruslan <h.turpal@gmail.com>
- Name-status: `A RC030_COMMIT_APPROVAL_DEVIATION.md`, `A RC030_DATA_DEPENDENT_TEST_RCA.md`, `A RC030_TEST_PORTABILITY_VERIFICATION.md`, `M tests/dose_verification_sandbox/test_evidence_integrity.py`, `M tests/dose_verification_sandbox/test_invariants.py`
- Stat: 5 files changed, 175 insertions(+), 2 deletions(-)
- Repository status after commit: only this commit's five files left the working tree; all other untracked P5.6/RC-030 audit artifacts from prior turns remain untracked and unstaged (unchanged by this commit).

## Bare fresh-clone validation (new scratch directory, no manual DB copy)

- `git rev-parse HEAD` in the clone → `394818675b0ed199e03cae1d89e38a488f5102ce` — matches.
- `uv lock --check` → `Resolved 194 packages` — lock file consistent with `pyproject.toml`.
- `uv sync --frozen --extra tests --extra clinical` → clean install, no resolution changes.
- Targeted RC-030/sandbox suite: **95 passed, 3 skipped, 0 failed, 0 errors.** No `OperationalError`, no `FileNotFoundError`. Skips: the two newly-gated real-corpus checks plus one pre-existing gated check (`test_review_tasks_have_no_consensus_or_qa_verdict`) — all explicit, all for absent optional data.
- Canonical collection: **1456 tests** — unchanged (the sandbox suite has never been part of `[tool.pytest.ini_options].testpaths`, so this number is independent of the portability fix).
- Full canonical pytest: **1444 passed, 11 skipped, 1 xfailed, 0 failed** — identical to the `dd8b3ad` baseline recorded in `RC030_COMMIT_B_POSTCOMMIT_VERIFICATION.md`.
- External-path dependency scan of `tests/`: 0 matches for `C:\ANTIBIO`, `C:\clinrec_downloader`, `C:\Users\<name>`, `/home/`, `/Users/`.
- No `.sqlite`/`.db` file was created anywhere in the clone by the test run.

## Post-commit invariants (executed against the committed code)

- `TYPES_MEETING_PRECISION_THRESHOLD` → `set()` (empty), imported directly from the fresh clone's `dose_verification_sandbox/validation_status.py`.
- No new import of `dose_verification_sandbox`/`semantics_*` appears outside `dose_verification_sandbox/` or its test directory except the pre-existing `evidence/generate_regimen_5574_evidence.py` (direct DB query, no semantics-code import).
- `git diff --stat dd8b3ad HEAD` shows only the 5 intended files — **no production/calculation code** (`calculator.py`, `semantics_parser.py`, `validation_status.py`, etc.) changed between the two commits.

## Real main-checkout invariants (read-only, not part of this commit)

- `assembled_regimens.sqlite` SHA-256 `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9` — unchanged.
- `normalized_regimens.sqlite` SHA-256 `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237` — unchanged.
- `review_workbench_p56.sqlite`: `review_decisions` = 0 rows; all 9,153 `review_tasks` rows = `PENDING`. Approved objects = 0.

## Result

Portability fix committed, verified from a bare fresh clone using `uv.lock`, with zero manual database restoration required for the targeted suite and zero regression in the canonical suite. This report itself is **not included** in commit `3948186` (it was generated after the commit) and is left as an untracked file pending a later documentation commit and owner classification.
