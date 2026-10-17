# Dependency Lock Verification — Phase 7

Generated: 2026-07-15.

## Authoritative dependency files

- **`pyproject.toml`** — canonical project + dependency spec, `requires-python = ">=3.12,<3.13"`, `[tool.uv] package = false`
- **`uv.lock`** — canonical lock file, `requires-python = "==3.12.*"`, lockfile schema `version = 1`, `revision = 3`

## Environment used for this verification

- `python --version` → `Python 3.12.10` (matches `>=3.12,<3.13` constraint)
- `uv` binary is **not present on PATH** in this shell — lock regeneration/verification via `uv lock --check` could not be executed directly in this session. Verification below instead cross-checks currently-installed package versions against `pyproject.toml` constraints.
- Installed versions confirmed compatible: `pytest 9.1.1` (constraint `>=9.0,<10` ✓), `pydantic 2.13.4` (`>=2.13,<3` ✓), `httpx 0.28.1` (`>=0.28,<1` ✓), `orjson 3.11.9` (`>=3.11,<4` ✓), `fastapi 0.139.0` (`>=0.135,<1` ✓)
- `uv.lock` contains a resolved entry for `accelerate 1.14.0` and other heavyweight ML packages, consistent with the `semantic`/`layout`/`extraction` optional groups in `pyproject.toml`.

## Optional dependency groups (from `pyproject.toml`)

| Group | Purpose | Weight |
|---|---|---|
| `clinical` | `fastapi`, `uvicorn` — Clinical Engine API surface (disconnected per this program's scope) | light |
| `extraction` | `pymupdf==1.24.10`, `pillow`, `docling==2.112.0`, `mineru==3.4.4`, `tqdm` — PDF corpus extraction | medium |
| `layout` | `albumentations`, `doclayout-yolo==0.0.4`, `matplotlib`, `rapid-table==3.0.2`, `seaborn`, `table-transformer==1.0.6` — OCR/layout ML | heavy |
| `semantic` | `huggingface-hub`, `torch==2.4.1`, `torchvision==0.19.1`, `transformers==4.57.6` | heavy |
| `tests` | `pytest>=9.0,<10`, `pytest-asyncio`, `pytest-cov`, `respx`, plus `pillow`/`pymupdf` for fixture support | light |
| `development` | `mypy`, `ruff` | light |

`[tool.uv].override-dependencies` pins `pillow>=11,<13` and `tqdm>=4.67.1,<5` project-wide to resolve a known conflict between `table-transformer` (which wants older pins) and current MinerU/Docling (which want newer ones) — documented in the `pyproject.toml` comment and load-bearing for the `layout` + `extraction` groups.

## Test collection sanity check

`pytest --collect-only -q` against the current environment collected **1387 tests** across the five `testpaths` declared in `pyproject.toml` (`medical_normalizer/tests`, `clinical_engine/tests`, `clinical_engine/regimen/tests`, `clinical_engine/review_workbench/tests`, `src/tests`) with zero collection errors. This confirms the `tests` optional-dependency group, as currently installed, is sufficient for the canonical test surface — a stronger signal than reading the lock file alone.

**Update 2026-07-15 (post personal-path fix):** collection now reports **1396 tests** (+9), the increase being `src/tests/test_extraction_site_packages.py`, added as regression coverage for the `ANTIBIO_EXTERNAL_SITE_PACKAGES` fix in `src/pipeline/extraction/layout.py`/`semantic.py`. Full targeted run (`test_layout_table_provenance.py` + `test_document_extraction.py`, including the real-model, non-skipped path): **13 passed**. `clinical_engine/regimen/tests` + `clinical_engine/review_workbench/tests`: **93 passed**. New regression file: **9 passed**. Zero regressions from the fix.

## Required facts

- **Install command (core only):** `uv sync` (installs base `dependencies` only, per `pyproject.toml`)
- **Install command (test environment):** `uv sync --extra tests`
- **Install command (full development):** `uv sync --extra tests --extra development --extra clinical`
- **Install command (heavyweight/ML, only if extraction/layout/semantic work is needed):** `uv sync --extra extraction --extra layout --extra semantic`
- **Supported Python version:** `3.12.x` only (`==3.12.*` in lock, `>=3.12,<3.13` in project) — 3.13 is explicitly out of range
- **Lock generation command:** `uv lock`
- **Lock verification command:** `uv lock --check` (confirms `uv.lock` is up to date with `pyproject.toml` without modifying it) — **not executed in this session** because `uv` is not installed in this shell; this is a gap the fresh-clone validation (Phase 13) must close by installing `uv` first
- **Core-only environment:** base `dependencies` list (7 packages: httpx, orjson, psutil, pydantic, pyyaml, rich, tenacity) — no ML, no test runner
- **Full-development environment:** `tests` + `development` + `clinical` extras
- **Heavyweight optional groups:** `extraction`, `layout`, `semantic` — each pins ML/CV packages (torch, transformers, docling, mineru, table-transformer) that are large downloads and Windows-sensitive; not required for the canonical non-ML test suite

## Gap flagged for Phase 13 (fresh clone)

`uv` itself must be installed in the fresh-clone environment before dependency installation can be validated end-to-end (`pip install uv` or the official installer). This was not verifiable from inside the current shell and is carried forward as an explicit fresh-clone prerequisite rather than assumed.
