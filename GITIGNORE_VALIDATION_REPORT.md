# .gitignore Validation Report — Phase 5

Generated: 2026-07-15. Current `.gitignore` was inspected as-is (no edits made in this phase — it already covers the required categories from prior work).

## Current `.gitignore` coverage (verified via `git check-ignore -v`)

| Required exclusion | Pattern present | Verified ignored |
|---|---|---|
| `.env` and credential files | `.env`, `.env.*`, `!.env.example`, `*.pem`, `*.key`, `credentials*.json`, `secrets*.json` | yes (`.env.example` correctly **not** ignored via negation; no real `.env` exists to test against) |
| Virtual environments | `.venv/`, `venv/` | yes — `.venv` confirmed excluded from untracked-file listing |
| Python caches | `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` | yes — `.mypy_cache/3.12/cache.0.db` confirmed ignored |
| Local IDE state | `.vscode/`, `.idea/` | present (not independently re-tested; no such dirs exist in this tree) |
| Logs / temp files | `*.log`, `*.tmp`, `temp_*/` | present |
| SQLite journal/WAL | `*.db-wal`, `*.db-shm` | present |
| Runtime databases | `*.sqlite`, `*.sqlite3`, `*.db` | yes — `kb_p44.db`, `assembled_regimens.sqlite`, `review_workbench_p56.sqlite`, `kb_final.db` all confirmed ignored |
| PDF corpus | `*.pdf` | yes — 7 PDFs present in tree, all excluded from untracked listing |
| Backups | `backups/` | yes — `backups/p5_6_baseline_20260715/kb_p44.db` confirmed ignored |
| Downloaded ML models | `models/`, `weights/`, `*.pt`, `*.pth`, `*.onnx`, `*.safetensors` | present (no such files currently exist to test against) |
| Generated milestone metrics / local review exports | `/quality_audit_data.json`, `/regimen_review_ledger.json`, `/field_statistics.csv`, `/unknown_drugs.csv`, and others | yes — all confirmed ignored |

## Must-not-ignore checks (source/tests/migrations/schemas/fixtures/docs/config must remain trackable)

| Path | Result |
|---|---|
| `src/tests/test_normalizer.py` | **not ignored** — correctly trackable |
| `clinical_engine/regimen/tests/__init__.py` | **not ignored** — correctly trackable |
| `pyproject.toml` | **not ignored** — correctly trackable |
| `uv.lock` | **not ignored** — correctly trackable |
| `db/antibio_db.json` | **not ignored** — correctly trackable |
| `AGENTS.md` | **not ignored** — correctly trackable |
| `.env.example` | **not ignored** (negation rule works) — correctly trackable |

No false-positive ignores were found against this spot-check set.

## Gaps identified (original pass) — now resolved per owner decisions of 2026-07-15

- `medical_dictionary/unknown_drugs.csv` is a **different file** from the root-anchored `/unknown_drugs.csv` pattern (line 83). **Resolution:** owner decision 2 classifies it as a legacy/runtime artifact (GENERATE DURING BUILD), excluded from the recovery commit at the file-list level (`REPOSITORY_RECOVERY_CLASSIFICATION.csv`, `P56_PROPOSED_TRACKED_FILES.txt`) rather than via a new `.gitignore` pattern — see [UNKNOWN_DRUGS_CSV_DECISION.md](UNKNOWN_DRUGS_CSV_DECISION.md). No `.gitignore` change was needed or made for this file.
- `p56_queue_report.json` and `p56_review_benchmark.json` (repo root) did not match any existing ignore pattern. **Resolution (owner decision 6): fixed.** Added two root-anchored lines to `.gitignore`:

  ```
  # P5.6 Phase 5/8: review-workbench benchmark/queue dumps (output-only defaults in
  # benchmark_review_workbench.py, build_review_workbench.py, generate_review_workbench_report.py)
  /p56_queue_report.json
  /p56_review_benchmark.json
  ```

  Verified minimal and correct via `git check-ignore -v`:

  ```
  .gitignore:89:/p56_queue_report.json	p56_queue_report.json
  .gitignore:90:/p56_review_benchmark.json	p56_review_benchmark.json
  ```

  Confirmed, before applying: both filenames are **write-only defaults** (`--out`/`--report` argument defaults) in their producer scripts — grep found no code path that *reads* either filename back in, so gitignoring them cannot break any consumer.

## Post-fix re-verification: source/tests/config/docs remain addable

Re-ran `git check-ignore -q` against a representative set after the two-line addition — all still correctly **not** ignored: `src/tests/test_normalizer.py`, `clinical_engine/regimen/tests/__init__.py`, `pyproject.toml`, `uv.lock`, `.env.example`, `db/schema.json`, `AGENTS.md`, `README.md`, `medical_dictionary/dictionary_candidates.json`. No source, test, migration, schema, fixture, or documentation path was affected by this change.

## Recommendation

`.gitignore` now correctly excludes all required categories, including the two Phase 5 gaps, with the minimum additive change (two root-anchored lines) and no broadening that could hide source code.
