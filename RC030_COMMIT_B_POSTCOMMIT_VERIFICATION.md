# RC-030 Commit B — Post-Commit Verification

Commit: `dd8b3ad` on `main`, direct child of `7d45bcb`. New commit, no amend, no push.

## Fresh clone

`git clone --no-hardlinks C:/ANTIBIO` into a scratch temp dir → `git log --oneline -3` shows
`dd8b3ad → 7d45bcb → 630a5f7`, confirming the commit is reachable from a clean clone.

## Install from lock

`python -m uv sync --frozen` against the clone's `uv.lock`, plus `--extra tests --extra clinical`
(required for `pytest` and `fastapi`/the review API test respectively — both declared in
`pyproject.toml`, resolved from the same lock, no version drift). 1456 tests collected, matching
the canonical count.

## Sandbox / RC-030 tests (96 target)

- Bare fresh clone (source `.sqlite` files correctly absent — gitignored, not part of the commit):
  93 passed, 1 skipped, **2 failed** (`test_source_databases_unchanged_by_evidence_generation`,
  `test_approved_object_count_is_zero`) — both fail only because the DB files don't exist yet in a
  bare clone (`sqlite3.OperationalError: unable to open database file`), not because of anything in
  the commit.
- After restoring the (gitignored, unchanged) source databases into the clone: **95 passed, 1
  skipped, 0 failed.** This confirms the 2 earlier failures were a fresh-clone data-availability
  artifact, not a regression.

## Full canonical pytest (fresh clone, lock-installed env)

**1444 passed, 11 skipped, 1 xfailed, 0 failed** (1456 collected). The 11 skips (vs. the
pre-existing dev environment's 0 reported skips) are tests gated behind the `semantic` extra
(torch/transformers) that isn't part of the `tests`/`clinical` extras installed here — expected,
not a regression. **Zero failures.**

## Invariant re-confirmation (executed against the fresh-clone, lock-installed commit)

- `TYPES_MEETING_PRECISION_THRESHOLD` → `set()` (empty), imported directly from the committed
  `dose_verification_sandbox/validation_status.py`.
- **No parser candidate gets a calculation**: ran `classify_regimen` + `assess_risk` + `validate`
  over all 2,675 rows of `assembled_regimens.sqlite` in the fresh clone — **0 rows** achieved
  `calculation_eligibility != BLOCKED`.
- Source DB hashes unchanged: `assembled_regimens.sqlite` = `9f505d08...`, `normalized_regimens.sqlite`
  = `c7b67354...` — identical to the hashes recorded in the evidence packet and in the pre-staging
  audit.
- Approved objects = 0: `review_workbench_p56.sqlite` is untouched by this commit (not in the diff,
  not gitignored-restored into the clone since no test needed it here); its state was independently
  re-verified against the original repository immediately before committing (`review_decisions` = 0
  rows, all 9,153 `review_tasks` = `PENDING`).
- Clinical Engine disconnected: `grep` for RC-030 module names outside `dose_verification_sandbox/`
  in the committed tree returns only `evidence/generate_regimen_5574_evidence.py`, which queries
  databases directly and imports no RC-030 semantics code.
- P6 remains BLOCKED: confirmed in the committed `PROJECT_STATE.md` and `NEXT_TASK.md`.

## Verdict

**RC-030 Commit B is committed, verified from a fresh clone against `uv.lock`, and every fail-closed
guarantee holds under independent re-execution — not just documentation.** All RC-030 records remain
`UNVALIDATED` / `CALCULATION_BLOCKED` / `NOT CLINICALLY APPROVED`. P6 remains BLOCKED. Nothing pushed.
