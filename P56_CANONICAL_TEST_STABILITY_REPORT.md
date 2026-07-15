# Canonical Test Stability Report

Generated: 2026-07-15.

## Fix applied

`clinical_engine/terminology.py`, `BasicTerminologyProvider.__init__`: `self._atc_map = load_drug_atc()` → `self._atc_map = dict(load_drug_atc())` — a defensive copy of the `@lru_cache`-cached dict before the subsequent `.setdefault("unmapped_pen", ...)` mutates it. Full root cause: `MEDICAL_DICTIONARY_TEST_ISOLATION_RCA.md`.

Additional real-database hygiene fix: `clinical_engine/review_workbench/tests/test_rc027_packet_provenance.py::test_stale_target_version_rejected_still_holds` previously called `service.claim(..., reviewer="r1", ...)` directly against the **real** `review_workbench_p56.sqlite`, and since `r1` was never registered, every run wrote a `REVIEWER_NOT_REGISTERED` row into that real database's `review_rejected_attempts` table (9 such rows had accumulated from this session's earlier test invocations — deleted; see Phase 8 note below). Fixed by registering the synthetic `r1` reviewer in the test's already-present in-memory `ReviewerRegistry` first, so the stale-revision check (not registry validation) is what rejects the call, and no write to the real store's audit table occurs.

Regression test added: `clinical_engine/tests/test_terminology_cache_isolation.py` (2 tests) — proves constructing `BasicTerminologyProvider` does not mutate the shared cache, and that repeated construction does not accumulate state.

Root Cause Register: **RC-029**, added and marked FIXED in `ROOT_CAUSE_REGISTER.md`.

## Repeated canonical runs (post-fix)

| Run | Command | Result | Duration |
|---|---|---|---|
| 1 | `python -m pytest -m "not slow and not corpus and not ml" -q` | **1453 passed, 1 xfailed, 0 failed** | 576.33s |
| 2 (previously-contaminating order, full scale) | `python -m pytest clinical_engine/ medical_normalizer/ src/tests/ -m "not slow and not corpus and not ml" -q` | **1453 passed, 1 xfailed, 0 failed** | 580.89s |
| 3 (second consecutive canonical run) | `python -m pytest -m "not slow and not corpus and not ml" -q` | **1453 passed, 1 xfailed, 0 failed** | 417.32s |

All three runs report **identical pass/xfail counts** (1453/1). Collection count stable at **1454 tests** (`python -m pytest --collect-only -q`) across repeated invocations. Zero collection errors. No new skip or xfail was added — the single pre-existing `xfailed` test is unrelated to this investigation (unchanged from before this session).

**No broad skip/xfail was introduced. No test-order pinning was applied — the fix removes the order-dependency at its source (the mutation), so no specific invocation order is required for the suite to pass.**

## Direct reproduction of the fix (outside pytest)

```
>>> from medical_dictionary.loader import load_drug_atc
>>> load_drug_atc()
{}
>>> from clinical_engine.terminology import BasicTerminologyProvider
>>> from clinical_engine.pipeline import ClinicalConstants
>>> provider = BasicTerminologyProvider(ClinicalConstants(age_bands={}, renal_thresholds={}, allergy_class_map={}, allergy_class_hierarchy={}))
>>> load_drug_atc()
{}
>>> load_drug_atc() is provider._atc_map
False
```

## Real-database integrity re-verified after all repeated test runs

| Check | Result |
|---|---|
| `review_rejected_attempts` rows | **0** (cleaned; confirmed no new pollution from the 3 repeated full-suite runs above) |
| `review_decisions` rows | 0 |
| `review_assignments` rows | 0 |
| Non-PENDING tasks | 0 |

## Conclusion

The canonical test suite is stable and clean across repeated, independent invocations in multiple orderings, both before the fix (in the true canonical order, where the defect was never observable) and after the fix (in every order tested, including the order that previously reproduced the failure). Closure Phase 5 requirement is satisfied.
