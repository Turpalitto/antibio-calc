# P5.6 Phase 13 — Fresh Clone Reproducibility Report

Generated: 2026-07-15, after `APPROVE P5.6 REPOSITORY RECOVERY COMMIT`.

## Clone

- **Command:** `git clone /c/ANTIBIO /c/antibio-fresh-clone` (local clone of the just-created commit; the commit has not been pushed to `origin`, so a clone from GitHub would not yet contain it — this local clone validates the exact commit that would be pushed).
- **Path:** `C:\antibio-fresh-clone`, fully outside `C:\ANTIBIO`, no hidden source files copied — only what `git clone` reconstructs from the commit object.
- **Commit cloned:** `32096af5ac1c1227027ef4075863164f45251139` (`chore(repository): restore reproducible ANTIBIO source tree`), confirmed via `git log`/`git rev-parse HEAD` in the clone.
- **Python version:** 3.12.10 (matches `requires-python = ">=3.12,<3.13"`).

## Hidden-dependency check

Grepped the fresh clone's `.py`/`.toml`/`.json`/`.yaml` source for the literal path `C:\ANTIBIO` or `C:/ANTIBIO`: **zero matches in code**. The only match anywhere is a prose mention inside `P56_OWNER_RECOVERY_BASELINE.md` (a historical audit document describing the original working directory, not a code dependency). **No hidden dependency on `C:\ANTIBIO` remains.**

## Dependency installation from locked source

- `python -m uv --version` → `uv 0.11.28` (installed via `pip install uv` since no standalone `uv` binary was on `PATH` — flagged in `DEPENDENCY_LOCK_VERIFICATION.md` as a fresh-clone prerequisite; resolved here).
- `uv venv --python 3.12` → created `.venv` in the fresh clone.
- `uv lock --check` → **"Resolved 194 packages"**, no drift between `pyproject.toml` and `uv.lock`.
- `uv sync --extra tests --extra clinical` → **36 packages installed cleanly** from the lock file (httpx, pydantic, pytest, fastapi, pymupdf, etc.), no network resolution surprises, no version conflicts.

## Import validation

```
import src.pipeline.extraction.layout
import src.pipeline.extraction.semantic
import src.pipeline.extraction.router
import clinical_engine.engine
import medical_normalizer.normalizer
```
**Result: OK, all imports clean** in the fresh venv — including the two modules patched for the personal-path fix.

## Test collection

`pytest --collect-only -q` in the fresh clone: **1396 tests collected**, zero collection errors — identical count to the source checkout (`C:\ANTIBIO`), confirming no file is missing from the commit that the test suite depends on.

## Key test suites (fresh clone, fresh venv)

| Suite | Result |
|---|---|
| `clinical_engine/regimen/tests` + `clinical_engine/review_workbench/tests` + `medical_normalizer/tests` + `src/tests/test_extraction_site_packages.py` | **917 passed, 8 skipped, 0 failed** (skips are environment-gated, e.g. real-model/heavyweight paths not installed in this lightweight `tests`+`clinical` sync — expected and correct for this profile) |

## Configuration fails safely without secrets

With all `ANTIBIO_*_API_KEY` variables removed from the environment, `create_provider()` (`src/llm/llm_provider.py`) raises:

```
RuntimeError: Missing required LLM credentials: ANTIBIO_DEEPSEEK_API_KEY, ANTIBIO_ANTHROPIC_API_KEY
```

Clear, actionable, names the missing variables — no crash, no hang, no silent fallback to invalid state.

## No dependency on untracked local files

The fresh clone contains no `.env`, no SQLite databases, no PDFs, no `unknown_drugs.csv`, no pilot-packet JSONs, no `.venv` from the source checkout (a new one was created fresh) — only what the commit tracks, plus the newly-created local `.venv` (itself gitignored, confirmed via `git status --short` showing no untracked entries in the clone).

## Total setup time

Clone: instantaneous (local). `uv venv` + `uv lock --check` + `uv sync --extra tests --extra clinical`: under 2 seconds combined. Full key-suite test run: 7.48s. Well under any reasonable threshold — this is a lightweight-profile validation; the heavyweight `extraction`/`layout`/`semantic` extras (torch, transformers, mineru, docling) were intentionally not installed here, consistent with `DEPENDENCY_LOCK_VERIFICATION.md`'s documented separation between the lightweight clinical/test profile and the heavyweight ML profile.

## External artifacts required (not present in this clone, by design)

- Clinical PDF corpus (`ANTIBIO_CORPUS_DIR`) — absent, as expected; not exercised by the lightweight suite run here.
- `kb_p44.db` / regimen SQLite stores — absent, as expected; `clinical_engine` tests that need them use fixtures under `clinical_engine/tests/fixtures/`, which are tracked and did run successfully.
- LLM provider credentials — absent by design; verified fail-safe above.

## Final verdict

**Fresh clone succeeds.** Dependencies install cleanly from the locked source (`uv.lock`), imports are clean, test collection count matches the source checkout exactly (1396), the key test suites pass with zero failures, credential-absence fails safely, and no hidden dependency on `C:\ANTIBIO` (or any file outside the committed tree) was found.
