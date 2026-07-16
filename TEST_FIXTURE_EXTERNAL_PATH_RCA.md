# TEST_FIXTURE_EXTERNAL_PATH_RCA.md

Status: Fresh-Clone Test Fixture Portability Fix, Phase 0. Read-only reproduction.

## Failing tests (fresh clone only)

```
FAILED src/tests/test_classifier.py::test_classify_level_a
FAILED src/tests/test_classifier.py::test_classify_level_c
FAILED src/tests/test_classifier.py::test_classify_level_b
```

Same tests pass (7/7) in the main checkout (`/c/ANTIBIO`, git commit `630a5f7`). Confirmed with two
direct runs: `python -m pytest src/tests/test_classifier.py -q` → `7 passed` in the main checkout;
`python -m uv run pytest src/tests/test_classifier.py -q` → `3 failed, 4 passed` in a fresh clone.

## Exact traceback (representative — `test_classify_level_a`)

```
def test_classify_level_a(sample_item, sample_pdf_text):
    with patch("classifier.detect_sections") as mock_detect:
        mock_detect.return_value = {...}
        result = classify_one(sample_item)

>   assert result["abx_level"] == "A"
E   AssertionError: assert 'D' == 'A'
```

Same shape for `test_classify_level_b` (expects `"B"`, gets `"D"`) and `test_classify_level_c`
(expects `"C"`, gets `"D"`).

## Fixture definition

`src/tests/conftest.py`:

```python
from config import BASE_DIR
...
@pytest.fixture
def sample_item():
    return {
        ...
        "pdf_path": str(BASE_DIR / "test.pdf"),
    }
```

`src/pipeline/config.py`:

```python
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "clinrec_downloader"
```

`Path(__file__)` is `src/pipeline/config.py`; four `.parent` calls walk up to the ANTIBIO repo's
**parent** directory, then into a sibling folder `clinrec_downloader` — i.e. `C:\clinrec_downloader\`,
**entirely outside the ANTIBIO git repository**. `sample_item`'s `pdf_path` therefore always resolves
to `C:\clinrec_downloader\test.pdf`.

## Why the main checkout passes

`C:\clinrec_downloader\test.pdf` exists on this development machine (835,683 bytes, confirmed present
by direct filesystem check) — it is a real, pre-existing file that happens to sit next to the
`ANTIBIO` checkout on disk, left over from this project's corpus-download tooling, but it is **not
tracked by git** (`git ls-files | grep test.pdf` → no match) and not part of the repository in any
form.

## Why the fresh clone fails

A `git clone` only reproduces tracked repository content. `C:\clinrec_downloader\` is a sibling
directory outside the cloned tree entirely — cloning `ANTIBIO` anywhere (a temp directory, a CI
runner, another developer's machine) will never bring this file along. `classifier.classify_one()`
short-circuits at line 56:

```python
def classify_one(item: dict[str, Any]) -> dict[str, Any]:
    pdf_path_str = item.get("pdf_path", "")
    if not pdf_path_str or not Path(pdf_path_str).exists():
        return {**item, "abx_level": "D", "confidence_score": 0, ..., "extraction_priority": "skip"}
```

When the file doesn't exist, `classify_one` returns the fixed "no PDF" result (`abx_level="D"`)
**without ever calling the mocked `detect_sections`**, regardless of what the test staged it to
return. Tests expecting `"A"`/`"B"`/`"C"` fail; `test_classify_level_d` (which itself expects `"D"`)
"passes," but for the wrong reason — it exercises the short-circuit path, not the real classification
logic it's nominally testing. This was true in the fresh clone before this fix.

## What the tests actually need

`classifier.detect_sections` is mocked (`patch("classifier.detect_sections")`) in every test in this
file that reaches the real classification logic. **The PDF is never opened, parsed, or read by any of
these tests.** The only requirement enforced by production code is `Path(pdf_path_str).exists()` —
a boolean existence check. No test asserts anything about PDF byte content, page count, or parsed
text (the "text" the tests exercise comes entirely from the mock's `return_value`, not from the file).

**Classification per Phase 1's taxonomy: B — existing empty (or trivially small) file.** No valid PDF
structure, no specific text, no specific metadata is required.
