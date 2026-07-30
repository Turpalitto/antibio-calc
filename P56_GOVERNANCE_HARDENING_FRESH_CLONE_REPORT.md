# Governance Hardening — Phase 13 Fresh Clone Validation

Generated: 2026-07-15.

## Clone

- **Command:** `git clone /c/ANTIBIO /c/antibio-fresh-clone-hardening` (local clone of the just-created commit; not pushed, so a clone from `origin` would not contain it).
- **Path:** `C:\antibio-fresh-clone-hardening`, fully outside `C:\ANTIBIO`. Deleted after validation.
- **Commit cloned:** `6e26aebce77d3d5c3ecb0a0b8689c766437d3636` — confirmed via `git log`/`git rev-parse HEAD`.

## Hidden-dependency check

Grep for `C:\ANTIBIO`/`C:/ANTIBIO` across `.py`/`.toml`/`.json` in the fresh clone: **zero matches in code.**

## Dependency installation from `uv.lock`

- `uv venv --python 3.12` → created `.venv`.
- `uv lock --check` → **"Resolved 194 packages"**, lock matches `pyproject.toml`.
- `uv sync --extra tests --extra clinical` → clean install, no conflicts.

## Import smoke test

```
import clinical_engine.review_workbench.reviewer_registry
import clinical_engine.review_workbench.service
import clinical_engine.review_workbench.storage
import clinical_engine.review_workbench.models
import clinical_engine.review_workbench.api
import clinical_engine.terminology
import clinical_engine.engine
```
**Result: clean**, including the new `reviewer_registry` module and the fixed `terminology` module.

## Canonical test collection

`pytest --collect-only -q` → **1454 tests collected**, identical to the source checkout, zero collection errors.

## Full canonical suite (lightweight profile: `tests` + `clinical` extras only)

`pytest -m "not slow and not corpus and not ml" -q`:

**`1442 passed, 11 skipped, 1 xfailed, 0 failed`** in 79.56s.

The 11 skips are environment-gated as expected in a fresh clone without the real review database or heavyweight ML extras (`extraction`/`layout`/`semantic` were not installed for this lightweight validation, matching `DEPENDENCY_LOCK_VERIFICATION.md`'s documented profile separation). The 1 xfail is the same pre-existing xfail present in the source checkout. **Zero unexpected failures.**

## Governance negative suite + synthetic positive workflow

`pytest clinical_engine/review_workbench/tests -v`:

**`108 passed, 8 skipped, 0 failed`** in 42.22s. The 8 skips are the real-database-gated tests (`test_real_review_artifact.py`, `test_rc027_packet_provenance.py`'s DB_PATH-conditional tests) — correctly skipped since `review_workbench_p56.sqlite` does not exist in a fresh clone (by design; it is a generated/external artifact, gitignored). **All 30 Phase-11 negative scenarios and the Phase-12 synthetic positive workflow test passed.**

## RC-029 regression (schema/cache-isolation fix)

`pytest clinical_engine/tests/test_terminology_cache_isolation.py -v`: **2/2 passed.** Confirms the `lru_cache` mutation fix holds in a completely fresh environment.

## Missing-secret fail-safe check

With all `ANTIBIO_*_API_KEY` variables removed:

```
RuntimeError: Missing required LLM credentials: ANTIBIO_DEEPSEEK_API_KEY, ANTIBIO_ANTHROPIC_API_KEY
```

Clear, actionable, no crash/hang — unchanged from the recovery-commit validation.

## No runtime DB required for unit tests

The 108 review-workbench tests that ran (all except the 8 real-DB-gated ones) required no `review_workbench_p56.sqlite` — every test constructs its own disposable `tmp_path`-scoped `ReviewStore`/`ReviewerRegistry`.

## No untracked source required

The clone contains only what commit `6e26aeb` tracks; no file from `C:\ANTIBIO` was copied in. All imports, tests, and checks above ran against the clone's own tracked content exclusively.

## No real clinical approval created

No task in any test run reached `PHYSICIAN_APPROVED` against real data — the synthetic positive workflow test operates entirely on a disposable `tmp_path` database created and destroyed within the test itself, never touching `review_workbench_p56.sqlite` (which doesn't exist in the clone at all).

## Final verdict

**Fresh clone succeeds.** Dependencies install cleanly from the locked source, imports are clean, test collection matches the source checkout exactly (1454), the full canonical suite and the full governance hardening suite both pass with zero unexpected failures, the RC-029 fix and the missing-credential fail-safe both hold, and no hidden dependency on `C:\ANTIBIO` or any untracked file was found.
