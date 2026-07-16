# RC-030 Data-Dependent Test Portability — Verification

## Fix summary

- `tests/dose_verification_sandbox/test_evidence_integrity.py`: added `test_synthetic_source_db_unchanged_by_readonly_evidence_query` (tmp_path SQLite fixture, no real data); renamed the hardcoded-hash test to `test_real_source_database_unchanged_by_evidence_generation` and gated it with `pytest.skip(...)` when the real DB is absent.
- `tests/dose_verification_sandbox/test_invariants.py`: added `test_synthetic_approved_object_count_is_zero` (tmp_path two-table SQLite fixture, no real data); renamed the original to `test_real_approved_object_count_is_zero` and gated it the same way.
- No change to `dose_verification_sandbox/calculator.py`, `semantics_parser.py`, `validation_status.py`, or any other RC-030 calculation-behavior file. No semantic type enabled.

## Regression run — bare fresh clone, zero manually restored databases

Clone of `dd8b3ad`, `.venv` synced from `uv.lock` (`--extra tests --extra clinical`), fixed test files overlaid (simulating the pending follow-up commit), **no `.sqlite`/`.db` files present anywhere in the clone**.

- `pytest tests/dose_verification_sandbox -v`: **95 passed, 3 skipped, 0 failed.**
  - Skips: `test_real_source_database_unchanged_by_evidence_generation`, `test_real_approved_object_count_is_zero` (both new gates, exact skip message: `"Optional corpus database not available; synthetic invariant test already covers deterministic behaviour."`), `test_review_tasks_have_no_consensus_or_qa_verdict` (pre-existing gate, unchanged).
  - No `sqlite3.OperationalError`, no `FileNotFoundError`, no silent empty-database use.
- `pytest -q --collect-only`: **1456 tests collected** — unchanged. `dose_verification_sandbox` is not in `[tool.pytest.ini_options].testpaths`, so the canonical suite's collection count is entirely independent of the sandbox test additions.
- `pytest -q` (full canonical): **1444 passed, 11 skipped, 1 xfailed, 0 failed** — identical to the pre-fix baseline (`RC030_COMMIT_B_POSTCOMMIT_VERIFICATION.md`).

## Invariant re-confirmation (same bare, DB-less clone)

- `TYPES_MEETING_PRECISION_THRESHOLD` → `set()` (empty), imported directly.
- Approved objects = 0 in **both** representations: the synthetic fixture (0 rows in `review_decisions`, all synthetic tasks `PENDING`) and, when the real DB is present, the real-corpus check (unaffected, still `pytest.skip`-gated when absent, still asserts `= 0` when the real file exists).
- Clinical Engine isolation unchanged: only `evidence/generate_regimen_5574_evidence.py` outside `dose_verification_sandbox/` references RC-030 module names, and it queries databases directly rather than importing semantics code.
- No test in the modified files depends on `C:\ANTIBIO` or any absolute path — both use `Path(__file__).resolve().parents[2]` (repo-relative) and `tmp_path` (pytest-managed temp dir).

## Result

The RC-030 targeted test suite (98 tests locally / 95 passed + 3 skipped in a database-less clone) now behaves correctly in a bare fresh clone with **zero manual database copying**, while still exercising the real corpus when it happens to be present in the working environment.
