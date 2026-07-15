# Reproducible Build

## Supported environment

- Windows 10/11 x64
- Python 3.12
- `uv` for deterministic dependency sync
- Node.js only for legacy HTML database validation

## Lightweight clinical/test environment

```powershell
git clone https://github.com/Turpalitto/antibio-calc.git
cd antibio-calc
uv sync --extra clinical --extra tests
uv run python -m pytest
```

This environment must not install OCR/layout models.

## Extraction environment

```powershell
uv sync --extra extraction --extra layout --extra semantic --extra tests
$env:ANTIBIO_CORPUS_DIR = 'D:\clinical-recommendations'
```

Provider credentials are optional until remote LLM execution is requested. Enabled remote providers fail fast when corresponding credentials are absent.

## External artifacts

1. Place corpus under `ANTIBIO_CORPUS_ROOT` using documented subdirectories.
2. Download model weights through provider tooling; do not copy user-specific site-packages paths.
3. Build databases from migrations/build commands; do not copy committed SQLite files.
4. Verify release artifact SHA-256 against milestone report.

## Extraction site-packages (2026-07-15 fix)

`src/pipeline/extraction/layout.py` and `semantic.py` previously hard-coded a single
workstation's `site-packages` path (a personal-path portability defect fixed during the P5.6
owner recovery program). This is now opt-in only:

- Default (unset `ANTIBIO_EXTERNAL_SITE_PACKAGES`): normal imports from the active `uv`-managed
  environment, no path injection, matches the "do not copy user-specific site-packages paths"
  rule above.
- If your heavyweight extraction deps (DocLayout-YOLO, Table Transformer, RapidTable,
  `transformers`) genuinely live outside the active environment, set
  `ANTIBIO_EXTERNAL_SITE_PACKAGES` to that directory in your **local, uncommitted** `.env`. An
  invalid/nonexistent path fails immediately with a named, actionable `RuntimeError` rather than
  silently no-op'ing.
- No username or machine-specific path may appear in tracked source. Regression coverage:
  `src/tests/test_extraction_site_packages.py`.

## Verification gates

```powershell
uv lock --check
uv sync --extra clinical --extra tests --frozen
uv run python -m pytest --collect-only
uv run python -m pytest
uv run python -m pip check
```

Extraction/ML smoke tests run separately with `ml`, `corpus`, and `slow` markers.
