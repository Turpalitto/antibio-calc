# Medical Dictionary Test Isolation — Root Cause Analysis

Generated: 2026-07-15.

## Reproduction of the canonical command

**The true canonical command, run exactly as specified, is 100% green:**

```
python -m pytest -v
```

Result: **`1451 passed, 1 xfailed, 304 warnings in 486.09s (0:08:06)`** — zero failures, full suite including `slow`/`corpus`/`ml`-marked tests (no `-m` filter applied). Interpreter: `Python 3.12.10` (`C:\Users\TURPAL\AppData\Local\Programs\Python\Python312\python.exe`). No `PYTEST_*`/`PYTHON*` environment variables set. No random-order plugin installed (`pytest-randomly` etc. absent from the plugin list) — pytest's collection order is deterministic, governed by `pyproject.toml`'s `testpaths = ["medical_normalizer/tests", "clinical_engine/tests", "clinical_engine/regimen/tests", "clinical_engine/review_workbench/tests", "src/tests"]`, i.e. **`medical_normalizer/tests` collects and runs first, before any `clinical_engine` test.**

**The one-failure result reported in the previous session (`1450 passed, 1 failed`) was produced by a non-canonical invocation** — `pytest clinical_engine/ medical_normalizer/ src/tests/ -m "not slow and not corpus and not ml"` — which lists `clinical_engine/` explicitly **before** `medical_normalizer/`, reversing the order `testpaths` specifies. This is confirmed by re-running the identical file set in the canonical `testpaths` order (`medical_normalizer/tests clinical_engine/tests clinical_engine/regimen/tests clinical_engine/review_workbench/tests src/tests`, same `-m` filter): **`1451 passed, 1 xfailed`** — zero failures.

**Per the instruction not to accept "pre-existing/flaky" without proof: the failure is real, reproducible on demand under a specific (non-canonical) order, and has a fully identified, non-nondeterministic root cause below — it is not flaky in the sense of being unpredictable.**

## Order dependency confirmed

Bisection (halving `clinical_engine/tests/*.py`, run before `medical_normalizer/tests/test_medical_dictionary_loader.py`) isolated the contamination to exactly two files, each independently sufficient to cause the failure:

- `clinical_engine/tests/test_engine.py`
- `clinical_engine/tests/test_golden_runner.py`

(`test_drug_reference_reader.py` and `test_guideline_verifier.py`, the two other files bisection initially grouped these with, do **not** independently reproduce it.)

## Root cause (Category A: production code global-state defect)

`medical_dictionary/loader.py`:

```python
@lru_cache(maxsize=1)
def load_drug_atc() -> dict[str, str]:
    """Return canonical drug name → ATC code. Empty until manual review."""
    data = _load_json("drug_atc.json")
    return dict(data["entries"])
```

`clinical_engine/terminology.py`, `BasicTerminologyProvider.__init__`:

```python
self._atc_map = load_drug_atc()
...
self._atc_map.setdefault("unmapped_pen", "J01CA04")
```

`functools.lru_cache` returns the **same dict object** on every call within a process. `BasicTerminologyProvider.__init__` then calls `.setdefault(...)` directly on that object — **mutating the shared, cached singleton in place**, rather than treating it as read-only or taking a defensive copy. Once any code constructs a `BasicTerminologyProvider` (which `test_engine.py::test_terminology_improves_allergy_exclusion` and `test_golden_runner.py`'s engine-construction fixture both do), `load_drug_atc()` permanently returns `{"unmapped_pen": "J01CA04"}` for the rest of the process — never `{}` again.

`medical_normalizer/tests/test_medical_dictionary_loader.py::TestLoaderDrugAtc::test_empty_until_review` asserts `load_drug_atc() == {}` — true "empty until manual review," per `drug_atc.json`'s own `description` field. This assertion is **correct** and must not be weakened; the defect is entirely on the production side.

## Direct proof (outside pytest, in a bare interpreter)

```python
>>> from medical_dictionary.loader import load_drug_atc
>>> load_drug_atc()
{}
>>> from clinical_engine.terminology import BasicTerminologyProvider
>>> from clinical_engine.pipeline import ClinicalConstants
>>> constants = ClinicalConstants(age_bands={}, renal_thresholds={}, allergy_class_map={}, allergy_class_hierarchy={})
>>> provider = BasicTerminologyProvider(constants)
>>> load_drug_atc()
{'unmapped_pen': 'J01CA04'}
>>> load_drug_atc() is provider._atc_map
True
```

This reproduces the corruption with zero pytest involvement — a plain Python session, one import, one object construction. This is not test-order superstition; it is a real, deterministic mutation bug.

## Classification

**A. Production code global-state defect.** (Secondarily manifests as C, test-order dependency — but the order-dependency is a *symptom*; fixing the mutation removes the order-dependency entirely, it does not require pinning test order.)
