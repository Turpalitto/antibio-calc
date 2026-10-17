# P5.6 Governance Hardening Closure — Final Report

Generated: 2026-07-15.

## 1. Initial canonical failure

Reported at the start of this closure program: `1450 passed, 1 failed` (`medical_normalizer/tests/test_medical_dictionary_loader.py::TestLoaderDrugAtc::test_empty_until_review`), described as "pre-existing/flaky." Per instruction, this was not accepted without proof.

## 2. Minimal reproducer

Direct reproduction outside pytest entirely:
```python
from medical_dictionary.loader import load_drug_atc
load_drug_atc()  # {}
from clinical_engine.terminology import BasicTerminologyProvider
from clinical_engine.pipeline import ClinicalConstants
BasicTerminologyProvider(ClinicalConstants(age_bands={}, renal_thresholds={}, allergy_class_map={}, allergy_class_hierarchy={}))
load_drug_atc()  # {'unmapped_pen': 'J01CA04'} — corrupted
```
Bisection isolated the pytest-level contamination to `clinical_engine/tests/test_engine.py` or `test_golden_runner.py` running before `medical_normalizer/tests` — which only happens under a **non-canonical** invocation order (the true canonical `python -m pytest`, per `testpaths` in `pyproject.toml`, runs `medical_normalizer/tests` first and was never actually red).

## 3. Root cause

**RC-029**: `clinical_engine/terminology.py`'s `BasicTerminologyProvider.__init__` mutated the `functools.lru_cache`-cached dict returned by `medical_dictionary.loader.load_drug_atc()` in place, via `.setdefault(...)`, permanently corrupting the process-wide singleton the first time any code constructed the provider. Classification: **A — production code global-state defect**.

## 4. Correction

`self._atc_map = load_drug_atc()` → `self._atc_map = dict(load_drug_atc())` (defensive copy). 3 insertions, 2 deletions. No clinical logic, dosing rule, or terminology mapping changed. Regression test added: `clinical_engine/tests/test_terminology_cache_isolation.py` (2 tests). Also fixed: a test (`test_rc027_packet_provenance.py::test_stale_target_version_rejected_still_holds`) that was writing synthetic `REVIEWER_NOT_REGISTERED` audit rows into the **real** `review_workbench_p56.sqlite` on every run — 9 accumulated rows were found, deleted, and the test fixed to register its synthetic reviewer in an in-memory registry so it can never touch the real store again.

## 5. Repeated full-suite results

| Run | Order | Result |
|---|---|---|
| 1 | True canonical bare `python -m pytest -v` (before fix, proves canonical order was never broken) | 1451 passed, 1 xfailed, 0 failed (486s) |
| 2 | Canonical order, fast subset (after fix) | 1453 passed, 1 xfailed, 0 failed (576s) |
| 3 | Previously-contaminating order, full scale (after fix) | 1453 passed, 1 xfailed, 0 failed (581s) |
| 4 | Second consecutive canonical run (after fix) | 1453 passed, 1 xfailed, 0 failed (417s) |

Collection count stable at 1454 throughout. No broad skip/xfail added. No test-order pinning required — the fix removes the order-dependency at its source.

## 6. Governance implementation verification (independent, direct source inspection)

All three original defects (GOV-001/002/003) and all supporting hardening (assignment revocation, immutable decisions, close semantics, stale-target protection, interaction-check immutability, Clinical Engine isolation) confirmed directly against code, not test results or prose — see `P56_GOVERNANCE_IMPLEMENTATION_VERIFICATION.md`. Notably: exactly one line in the entire codebase sets `ReviewState.PHYSICIAN_APPROVED`, and it is gated inside `submit_medical_qa_signoff`.

## 7. Migration reproducibility

Reproduced on disposable copies of the verified pre-migration backup (never the sole live database): task IDs, target versions, and states preserved exactly; 0 decisions invented; migration proven idempotent (byte-identical on re-run); rollback/restore procedure tested and confirmed functional. See `P56_REVIEW_DB_MIGRATION_REPRODUCIBILITY_REPORT.md`.

## 8. Real database final state

`review_workbench_p56.sqlite`: schema version **2**, `PRAGMA integrity_check` = `ok`, **9,153** tasks (100% PENDING, 0 changed), **0** assignments, **0** decisions, **0** rejected-attempt rows (cleaned after the test-hygiene fix), **0** approved objects. No reviewer registry file exists anywhere in the repository — **0 real reviewers**.

## 9. Files committed

44 files (20 modified, 24 added), 3,360 insertions(+), 175 deletions(-). Full list: `P56_GOVERNANCE_HARDENING_PROPOSED_ALLOWLIST.txt` / `P56_GOVERNANCE_HARDENING_STAGED_AUDIT.md`. No database, PDF, model, `.env`, or pilot-packet file staged. `clinical_engine/engine.py` and all frozen bundle-manifest/schema files: untouched.

## 10. Commit hash

`6e26aebce77d3d5c3ecb0a0b8689c766437d3636`
Parent: `32096af5ac1c1227027ef4075863164f45251139`
Branch: `main`. **Not pushed** (`ahead 3` of `origin/main`, unchanged push status). Recovery commit `32096af` was not amended.

## 11. Fresh-clone result

Cloned commit `6e26aeb` into an isolated directory (deleted after validation). `uv lock --check` clean, dependencies installed from lock, import smoke test clean, collection **1454** (matches source exactly), full canonical suite (lightweight profile) **1442 passed / 11 skipped / 1 xfailed / 0 failed**, governance test suite **108 passed / 8 skipped / 0 failed** (all 30 negative scenarios + the synthetic positive workflow), RC-029 regression **2/2 passed**, missing-credential fail-safe confirmed, zero hidden dependency on `C:\ANTIBIO` or untracked source. See `P56_GOVERNANCE_HARDENING_FRESH_CLONE_REPORT.md`.

## 12. Reviewer registry state

Empty. `pilot_status = WAITING_FOR_REVIEWERS`. No reviewer, real or synthetic, is registered anywhere in the committed source or the real database.

## 13. Pilot task state

All 30 pilot tasks (20 ClinicalRegimen + 10 TherapeuticOption): **PENDING**, unchanged throughout this entire closure program.

## 14. Approved-object count

**0**, database-wide (9,153 tasks), unchanged throughout.

## 15. Clinical Engine isolation

Zero import of `review_workbench` anywhere in `clinical_engine/engine.py`, `pipeline.py`, `readers/`, `api/` — re-verified independently multiple times this session, most recently inside the fresh clone.

## 16. Remaining blockers

1. No real Reviewer A, Reviewer B, or Medical QA Lead is registered — the owner must do this via `ReviewerRegistry.register(...)` per `REVIEWER_IDENTITY_AND_ASSIGNMENT_POLICY.md`.
2. Two prior post-recovery evidence documents (`P56_STAGED_CONTENT_AUDIT.md`, `FRESH_CLONE_REPRODUCIBILITY_REPORT.md`) plus this program's own evidence were committed as governance evidence in this commit — no further action needed there.
3. `ClinicalCorrectionProposal` mechanism (pilot mandate Phase 9) still does not exist — not needed until real reviewers begin identifying errors.

## 17. P5.6 status

Repository recovery: complete. Fresh-clone validation: complete (twice, both the recovery commit and this hardening commit). Governance hardening: complete, independently verified, committed, fresh-clone-validated. **Physician review pilot has still not begun** — waiting on real reviewer registration.

## 18. P6 status

**BLOCKED.** Unchanged. No push performed.

---

## Exit gates — verified

✔ canonical failure has proven root cause (RC-029, reproduced outside pytest) · ✔ isolation regression fixed (defensive copy + regression test) · ✔ full pytest passes at least twice consecutively (4 clean runs total, 2 in the identical canonical invocation) · ✔ no broad skip/xfail added · ✔ GOV-001 independently verified · ✔ GOV-002 independently verified · ✔ GOV-003 independently verified · ✔ migration reproducible on copies · ✔ real DB remains clinically untouched (and a test-induced hygiene issue was found and fixed) · ✔ all 30 pilot tasks remain PENDING · ✔ real reviewer count remains 0 · ✔ approved objects remain 0 · ✔ Clinical Engine remains disconnected · ✔ hardening committed separately (not amended onto the recovery commit) · ✔ fresh clone passes full canonical suite · ✔ no hidden source dependency remains · ✔ no push performed

## Final verdict

**A) GOVERNANCE HARDENING CLOSED — PILOT MAY REGISTER REAL REVIEWERS**

P6 remains BLOCKED.
