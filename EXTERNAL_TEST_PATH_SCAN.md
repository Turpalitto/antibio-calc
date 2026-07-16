# EXTERNAL_TEST_PATH_SCAN.md

Status: Fresh-Clone Test Fixture Portability Fix, Phase 4. Full scan of tracked `.py`/`.md`/`.json`
files for external-path references. Read-only.

## Method

```
git grep -n "clinrec_downloader" -- '*.py'
git grep -ln "C:\\Users\\" -- '*.py' '*.md' '*.json'
```

`C:\Users\` search returned **zero matches** in tracked files — no personal-account paths anywhere in
the repository. `C:\ANTIBIO` absolute self-references were checked separately (see below).

## `C:\clinrec_downloader` references — classified

### Production configuration / CLI tooling (legitimate, documented, not a test defect)

`clinical_engine/corpus/locator.py` is the canonical documentation for this pattern: *"a large
research asset stored OUTSIDE git at `C:\clinrec_downloader`"* — the corpus (hundreds of PDFs) is
deliberately never committed to git (too large, and likely license-sensitive source material). The
following are production/maintenance scripts, not tests, meant to be run interactively by a developer
who has the real corpus checked out locally, with `C:\clinrec_downloader` as a sensible, overridable
default:

```
main.py, build_p44_kb.py, build_review_workbench.py, production_reprocessor.py,
reprocess_p45_layout.py, restore_archived_pdfs.py, validate_full_corpus.py,
src/pipeline/config.py (BASE_DIR), src/pipeline/prefilter.py,
src/pipeline/extraction/semantic_yield_audit.py,
clinical_engine/corpus/locator.py, clinical_engine/tools/build_diagnosis_index_draft.py,
clinical_engine/tools/build_normalized_sqlite.py, clinical_engine/tools/clinical_data_audit.py,
clinical_engine/tools/performance_audit.py
```

**Classification: production configuration / documented optional override.** No action needed — these
are not test-reproducibility defects; they are meant to be pointed at a local corpus copy by the
person running them.

### Test files referencing the corpus — already correctly gated

```
clinical_engine/regimen/tests/test_p53_assembly.py
clinical_engine/regimen/tests/test_p54_quality_improvement.py
clinical_engine/regimen/tests/test_p55_class_level_separation.py
clinical_engine/review_workbench/tests/test_real_review_artifact.py
clinical_engine/tests/test_config.py
clinical_engine/tests/test_corpus_locator.py
src/tests/test_knowledge_base.py
src/tests/test_layout_table_provenance.py
```

Spot-checked four of these directly: every one calls `pytest.skip(...)` when the referenced corpus
path/PDF/database doesn't exist (`test_corpus_locator.py`: *"a missing corpus is handled gracefully"*
by design; `test_knowledge_base.py`: `if not pdf.exists(): pytest.skip(...)`;
`test_layout_table_provenance.py`: same pattern; `test_p53_assembly.py`: `pytest.skip("normalized_regimens.sqlite not available")`).
Consistent with the `corpus` marker already registered in `pyproject.toml`
(`corpus: requires external clinical corpus`). This is exactly the correct, intentional pattern for
an optional, large, ungitted asset — the canonical full pytest run in the fresh clone confirmed this:
these tests appeared among the **10 skipped**, not among the 3 failures. **Classification: documented
optional override, working as intended. No action needed.**

### Forbidden hidden dependency — found and fixed

```
src/tests/conftest.py — sample_item fixture (pdf_path = BASE_DIR / "test.pdf")
```

This was the **one** case in the entire scan where an external-corpus path was used **without** a
skip guard, in a fixture consumed by tests that hard-assert specific results. Fixed in this same pass
— see `TEST_FIXTURE_EXTERNAL_PATH_RCA.md`. This is the only entry in this scan classified **F:
forbidden hidden dependency**, and it is now resolved.

### Generated reports / benign text (out of scope, not source or test code)

Numerous `*.md` report files (`SESSION_HISTORY.md`, various `P4.x_*.md`, `RC030_*.md`, etc.) mention
`clinrec_downloader` in prose describing where PDFs were sourced from during this session's own
investigation work (e.g. `RC030_TARGETED_SOURCE_RECOVERY_REPORT.md`). **Classification: generated
report / benign text.** Not a reproducibility concern — these are historical narrative documents, not
code paths anything imports or executes.

## `C:\ANTIBIO` self-references

```
git grep -n "C:\\\\ANTIBIO" -- '*.py'  → no matches in source/test code
```

Only appears in generated `.md` reports (this session's own audit documents) describing absolute
paths for provenance/evidence purposes (e.g. `evidence/regimen_5574_verified_evidence.json`'s
generator script uses `Path(__file__).resolve().parents[1]`, a repository-relative construction, not
a hardcoded string — confirmed by reading `evidence/generate_regimen_5574_evidence.py`). **No
`C:\ANTIBIO` hardcoded string exists in any `.py` file.**

## Conclusion

One forbidden hidden dependency found and fixed (`src/tests/conftest.py`). Everything else matching
`C:\clinrec_downloader` is either legitimate production tooling configuration or already-correct,
already-gated optional test coverage. No further action required; scope not broadened beyond the
confirmed defect, per instruction.
