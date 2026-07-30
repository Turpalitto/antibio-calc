# P5.6 C7 Fresh-Clone Verification — 2026-07-30

## Verdict

**PASS.** Commit `5817a60ae63c581d6b1fe23f77b2105bf210783b`
is reproducible from a clean local clone with dependencies installed from
the committed lock file.

This is a technical repository gate only. It does not approve any regimen,
enter P6, or authorize Clinical Engine integration.

## Source identity

- clone source: local Git repository, `--no-local --no-hardlinks`;
- checkout: detached commit
  `5817a60ae63c581d6b1fe23f77b2105bf210783b`;
- checked-out tree:
  `2f11c7ad053d95319b382c210f1b538b2b09a27e`;
- initial checkout status: clean;
- tracked files: 788;
- no working-tree or untracked source was copied into the clone.

## Dependency verification

- uv: `0.11.32` (`3010295ae`, 2026-07-23);
- official Windows installer SHA-256:
  `D84B0D973693497F8C1C1D82B2D2F52E32E50C7C24EFA3D925341BD6FC5238B2`;
- installer mode: temporary unmanaged install; PATH and shell profiles were
  not modified;
- `uv lock --check`: PASS;
- command: `uv sync --extra clinical --extra tests --frozen --python 3.12`;
- Python: 3.12.10;
- installed from lock: 36 packages;
- import smoke for FastAPI, HTTPX, orjson, Pydantic, and pytest: PASS.

## Test results

### Canonical collection

`uv run --frozen --no-sync python -m pytest --collect-only -q`

- 1511 tests collected;
- zero collection errors;
- one Starlette/httpx deprecation warning.

### Canonical suite

`uv run --frozen --no-sync python -m pytest -q`

- 1499 passed;
- 11 skipped;
- 1 xfailed;
- 0 failed;
- one Starlette/httpx deprecation warning;
- elapsed: 31.95 seconds.

### C7 and portability suite

`uv run --frozen --no-sync python -m pytest
clinical_engine/tests/test_tool_corpus_portability.py
tests/rc030_owner_interface tests/dose_verification_sandbox -q -rs`

- 392 passed;
- 4 skipped;
- 0 failed;
- elapsed: 3.91 seconds.

All four skips are expected optional-artifact gates:

1. uncommitted optional owner control-sample dataset;
2. optional external corpus database, evidence-integrity check;
3. optional external corpus database, invariant check;
4. absent production `review_workbench_p56.sqlite`.

Synthetic invariant coverage remains active for the unavailable external
artifacts.

## Security and isolation

- tracked forbidden DB/PDF/private-key/real-env files: zero;
- tracked secret-pattern hits: zero;
- production DB/PDF copied into clone: zero;
- imports for `clinical_engine`, `medical_normalizer`, and `src.pipeline`
  resolve only inside the fresh clone;
- executable personal-home path hits: zero;
- one `C:\ANTIBIO` string remains in
  `src/pipeline/prefilter.py:35`, but it is a historical explanatory comment;
  path execution uses `Path(__file__)`, so it is not a hidden dependency;
- after tests, `git diff --quiet` returns success: tracked content is
  unchanged. Eight JSON files show Windows line-ending/stat noise in
  porcelain status after deterministic builders run, but their normalized Git
  content is unchanged.

## Remaining gates

- publish local commits to the configured remote when explicitly authorized;
- register real physician reviewers;
- complete the physician pilot;
- obtain physician-approved clinical objects;
- pass Golden validation on approved data;
- complete shadow/safety/request-audit gates;
- receive explicit owner authorization before P6/Engine integration.

P6 remains BLOCKED. Clinical Engine remains disconnected.
