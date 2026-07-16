# TEST_FIXTURE_PORTABILITY_FIX_REPORT.md

Date: 2026-07-16
Scope: Fresh-Clone Test Fixture Portability Fix

## Summary

| Phase | Output | Status |
|---|---|---|
| 0 | `TEST_FIXTURE_EXTERNAL_PATH_RCA.md` | Done — exact root cause: `sample_item.pdf_path` pointed to `C:\clinrec_downloader\test.pdf`, an untracked file outside the repository |
| 1 | Fixture-need classification | Done — Category B (existing file, no content/structure needed — `detect_sections` is mocked in every consuming test) |
| 2 | `src/tests/conftest.py` fix | Done — `sample_item(tmp_path)` writes a tiny, deterministic, marked `TEST_FIXTURE_ONLY` placeholder inside pytest's own `tmp_path`; `BASE_DIR` import removed |
| 3 | Regression tests | Done — 2 new tests in `test_classifier.py` proving the path is `tmp_path`-scoped and that classification works with `C:\clinrec_downloader` entirely absent |
| 4 | `EXTERNAL_TEST_PATH_SCAN.md` | Done — full scan; one forbidden hidden dependency found (the one fixed here); everything else is either legitimate production tooling config or already-correctly-`pytest.skip`-gated optional corpus tests |
| 5 | Regression | Main checkout: `src/tests/` 90 passed/1 xfailed; canonical collection 1,456; full canonical suite 1,455 passed/1 xfailed, exit 0. Isolated-copy portability check (see note below): 9/9 `test_classifier.py` pass from a directory with zero `C:\clinrec_downloader` presence |
| 6 | Commit boundary | This file — exact allowlist below, not staged |

## Note on Phase 5's "fresh clone" step

The fix is intentionally **uncommitted**, pending the same kind of explicit owner approval used for
the Dose Sandbox commit. A `git clone` only reproduces committed history, so a literal fresh clone
couldn't test uncommitted working-tree changes. Instead, verified the identical property (no
dependency on any path outside the test's own execution directory) by copying `src/` +
`pyproject.toml` + `uv.lock` to an isolated temp directory (`C:\Users\TURPAL\AppData\Local\Temp\portability_check`,
outside the repo, with no `C:\clinrec_downloader` reachable) and running the affected tests there
directly — 9/9 pass. One unrelated failure appeared in that narrow copy
(`test_document_extraction.py::test_semantic_processor_entities`) — confirmed **not** a regression by
running the same test in the full main checkout (passes there) and tracing it to a missing sibling
resource directory (`medical_dictionary/`) that the narrow copy didn't include — unrelated to
`clinrec_downloader` and unrelated to this fix.

## The fix

`src/tests/conftest.py`:
```python
@pytest.fixture
def sample_item(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 TEST_FIXTURE_ONLY\n")
    return {..., "pdf_path": str(pdf_path)}
```
No PDF is committed to the repository. The 27-byte placeholder is created fresh by every test run,
inside pytest's own per-test `tmp_path`, and is never read as a real PDF (every consuming test mocks
`classifier.detect_sections`, the only code that would parse it) — it exists solely so
`Path(pdf_path).exists()` returns `True`, which is the only thing production code checks.

## Proposed allowlist (Commit boundary — small, separate reproducibility commit)

```
src/tests/conftest.py                     (modified — sample_item fixture)
src/tests/test_classifier.py              (modified — +2 regression tests)
TEST_FIXTURE_EXTERNAL_PATH_RCA.md          (new)
EXTERNAL_TEST_PATH_SCAN.md                 (new)
TEST_FIXTURE_PORTABILITY_FIX_REPORT.md     (new, this file)
```

**Excluded** (confirmed absent from this diff by `git diff --stat`, checked above): RC-030 semantics
work, Dose Sandbox working-tree modifications, source databases, PDFs (no PDF file is added to git at
all — the fixture creates one dynamically at test time), generated logs.

**Not staged.** Stopping here per instruction, pending explicit owner approval.

## Final verdict

**A) PORTABILITY FIX READY FOR STAGING**

Root cause identified and fixed with the smallest possible change (2 files, 43 insertions / 3
deletions). No test semantics weakened — no test skipped, no `xfail` added, no exception swallowed;
the fix makes the tests exercise their *real* code path for the first time (previously
`test_classify_level_a/b/c` only worked in the main checkout because a file happened to exist outside
the repo; now they work everywhere, deterministically, by construction). Regression tests added prove
the property directly. Global scan found no other forbidden hidden dependency. Full regression clean
in the main checkout (1,455 passed, 1 pre-existing unrelated xfail, exit 0) and in isolation (9/9 for
the directly affected tests, with zero `C:\clinrec_downloader` reachable). Ready for staging on an
explicit owner approval command.

**P6 remains BLOCKED.**
