# Repository Recovery Classification — Phase 3 (updated Phase 8, post owner-decision pass 2026-07-15)

Generated: 2026-07-15, regenerated after owner decisions. Full per-file detail in [REPOSITORY_RECOVERY_CLASSIFICATION.csv](REPOSITORY_RECOVERY_CLASSIFICATION.csv) (520 unique files: 19 currently-tracked + 501 untracked non-ignored files, each with path, category, size, SHA-256, fresh-clone requirement, safe-to-commit flag, and reason).

`.venv/`, `__pycache__/`, `.mypy_cache/`, runtime databases, PDFs, and backups are already excluded by `.gitignore` and do not appear in this list — they were never candidates for tracking.

## Category counts (post owner-decision resolution)

| Cat | Meaning | Count | Safe to commit |
|---|---|---|---|
| A | production source code | 197 | yes |
| B | test source | 73 | yes |
| D | configuration template | 5 | yes |
| E | dependency/build metadata | 2 (`pyproject.toml`, `uv.lock`) | yes |
| F | documentation required for operation | 3 | yes |
| G | governance documentation (incl. this program's own 15 deliverable reports) | 36 | yes |
| H | reproducibility/build/tooling script | 13 | yes |
| J | manifest schema (`PILOT_BATCH_MANIFEST.json`, `PILOT_REVIEW_BATCH_V2_MANIFEST.json`) | 2 | yes |
| S | report/RFC/analysis doc | 121 | yes (owner decision 4: resolved — required governance/architecture/root-cause/reproducibility/production-readiness evidence) |
| — | pilot review packet exports (`pilot_review_batch*/crt_*.json`) | 62 | **no** — owner decision 3 |
| — | legacy/runtime artifacts (`unknown_drugs.csv` ×2) | 2 | **no** — owner decision 2 |
| — | transient/superseded (`SESSION_HISTORY.md`, `SESSION_SUMMARY.md`, `CORPUS_MANIFEST.json`, `REPOSITORY_UNTRACKED_INVENTORY.json`, `RECOVERY_TRACKED_FILES.txt`) | 5 | **no** — owner decision 4 |

**Total: 520 unique files. Proposed tracked: 452 (6.95 MB). Confirmed excluded: 68 (all individually decided, zero remain in an unresolved state).**

## Special-attention areas (per Phase 3 instructions, resolved)

- **`unknown_drugs.csv`**: both the root copy (gitignored) and `medical_dictionary/unknown_drugs.csv` (untracked) are excluded per owner decision 2 (GENERATE DURING BUILD; no producer script exists; classified legacy/runtime artifact). See [UNKNOWN_DRUGS_CSV_DECISION.md](UNKNOWN_DRUGS_CSV_DECISION.md).
- **`clinical_engine/regimen/`** and **`clinical_engine/review_workbench/`**: all category A/B, tracked, no exclusions.
- **Tests**: 73 files, all category B, all tracked, required for the 1387-test canonical suite.
- **Migration**: `clinical_engine/regimen/class_level_migration.py`, tracked.
- **Pilot batches**: 62 `crt_*.json` packet exports excluded per owner decision 3; the two manifest-schema files and both human-readable pilot reports (`PILOT_REVIEW_BATCH_REPORT.md`, `PILOT_REVIEW_BATCH_V2_REPORT.md`) are tracked.
- **`.claude/launch.json`**: tracked per owner decision 5 (no secret, no personal path, required for reproducible dev workflow, portable, no local IDE/session state).
- **Governance documents**: 36 files (up from 18 — now includes this program's own 15 P5.6 audit deliverables, which qualify as required security-incident-history/reproducibility/governance evidence).
- **SQLite/PDF/model/cache**: none in this list, all already gitignored.

## Personal-path defect — FIXED 2026-07-15

The previously-reported hardcoded `C:\Users\TURPAL\...` path in `src/pipeline/extraction/layout.py:41` and `semantic.py:17` has been patched per explicit owner instruction. Both files now use an opt-in `ANTIBIO_EXTERNAL_SITE_PACKAGES` environment variable (unset by default — normal imports from the active environment; validated and actionable-error-on-failure when set). Regression tests added: `src/tests/test_extraction_site_packages.py` (9 tests, all passing). Full targeted extraction test suite (13 tests, including the real-model path) and the review_workbench/regimen suite (93 tests) both pass unchanged, confirming behavior preservation.

### Requirement-6 sweep: remaining path/sys.path matches in the final tracked set

| Match | Classification |
|---|---|
| `src/pipeline/extraction/layout.py`, `semantic.py` | **Fixed** — no longer match any personal-path pattern |
| `AI_LOG.md:759` (mentions `C:\Users\TURPAL\...python.exe`) | Generated historical evidence — accurate log of a command actually run; not executable code |
| `PRODUCTION_READINESS_AUDIT_2026-07-15.md:292` | Generated historical evidence — documents the (now-fixed) defect as it existed at audit time |
| `docs/extraction/README.md:73-83` | Generated historical evidence — verification-session transcript, not a setup instruction for others to follow |
| `build_p44_kb.py`, `main.py`, `production_reprocessor.py`, `reprocess_p45_layout.py` (`sys.path.insert(0, str(Path(__file__).parent))`) | False positive — relative/dynamic path derived from `__file__`, not a hard-coded absolute literal |
| `src/tests/test_knowledge_base.py`, `test_layout_table_provenance.py` (`sys.path.insert(0, ".")` / `'.'`) | False positive — relative path literal, portable |
| `.env.example` (`ANTIBIO_CORPUS_DIR=C:\clinrec_downloader`) | Legitimate documentation example — a placeholder default in an example file meant to be overridden, contains no username |

No further portability defects found. Zero personal/machine-specific absolute paths remain in tracked production source.

## Zero unresolved classification categories

No file remains in category R, Q, or T. Every file has an explicit `safe_to_commit` value and reason. Final counts: **453 files tracked (6.96 MB), 66 excluded** (60 pilot packets + `unknown_drugs.csv` ×2 + `SESSION_HISTORY.md` + `SESSION_SUMMARY.md` + `CORPUS_MANIFEST.json` + `REPOSITORY_UNTRACKED_INVENTORY.json` + `RECOVERY_TRACKED_FILES.txt`).
