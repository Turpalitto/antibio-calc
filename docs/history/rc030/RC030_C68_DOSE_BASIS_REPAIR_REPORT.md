# RC-030 P5.6 C6.8 — Dose-Basis Semantics Repair, Source-Quote Attribution Correction, Full Range Replay and Owner-Queue Rebuild — Final Report

## 1-3. HEAD / commits

1. Starting HEAD: `fe7782d86e5b63ce9d574b86278d1b14d028bb13` (C6.7 final report, matched expected).
2. Final HEAD: `0cec60c`.
3. Commits created (in order, no amend, no rebase, no push):
   - `3351833` — C6.8-A: DoseUnitSignature model, structured compatibility repair, 49 new tests.
   - `cbafb2a` — C6.8-B: PDF hyphen-linewrap fix resolving the 5688/6052 source-quote defect.
   - `fd350c1` — C6.8-C: full 365/117 replay, V6 experimental artifact.
   - `0cec60c` — C6.8-D: owner queue rebuild, 2 new C5 modes.

## 4-6. Dose-unit model, vocabulary, compatibility rules

4. **DoseUnitSignature** (`dose_verification_sandbox/dose_unit_signature.py`): immutable dataclass with `numerator_unit`, `numerator_multiplier`, `weight_denominator`, `time_denominator`, `administration_basis`, `concentration_denominator`, `rate_basis`, `unknown_tokens`, `parse_status`. Validated field-by-field against all 8 of the spec's worked examples (`mg`, `mg/kg`, `mg/kg/day`, `mg/kg/dose`, `mg/day`, `mg/dose`, `mg/ml`, `mcg/kg/min`) — exact match on every field.
5. **Unit vocabulary audit**: real data queried directly — 13 distinct structured `unit` values across all 2675 assembled regimens; only genuinely-observed extended form in the 365-record corpus is `ЕД` (IU), 8 occurrences; `мкг`, `ммоль`, `м²`, `%`, drops: zero occurrences. Two real, previously-unhandled findings: `мкг/кг` structured values that are Cyrillic (not Latin-normalized, unlike `mg/kg`), and 3 rows with compound semicolon-separated multi-unit structured values (now correctly rejected as `MALFORMED_UNIT` rather than silently truncated).
6. **Compatibility rules**: `compare_dose_units()` returns one of 9 explicit outcomes (`EXACT_EQUIVALENT`, `COMPATIBLE_BASIS_UNSPECIFIED`, `INCOMPATIBLE_NUMERATOR`, `INCOMPATIBLE_WEIGHT_BASIS`, `INCOMPATIBLE_TIME_BASIS`, `INCOMPATIBLE_ADMINISTRATION_BASIS`, `CONCENTRATION_NOT_DOSE`, `RATE_NOT_DOSE`, `UNKNOWN_UNIT`, `MALFORMED_UNIT`). `COMPATIBLE_BASIS_UNSPECIFIED` never alone yields `SAFE_EXACT_LINK`.

## 7-11. Defects found

7. **Unit defect root cause**: `_base_unit()` (removed as dead code) compared only the token before the first `/`, so `mg`/`mg/kg`/`mg/kg/day` all collapsed to the same base unit `mg`. Compounded by the range regex having no alternative for the spelled-out Russian per-kilogram construction (`мг на кг массы тела в сутки`), silently truncating it to bare `мг`, and having no alternative at all for compact concentration forms (`мг/мл`), silently truncating those too.
8. **Affected records**: 14 originally flagged (C6.7); full individual re-audit in `RC030_C68_AFFECTED_14_REPORT.md`.
9. **The 6 previously-exact affected records**: 4 correctly downgraded (5917, 5918, 5441, 5442 — source text explicitly states "в сутки"/per-day, structured field doesn't); **2 correctly remained exact** (5475, 5478 — a genuine positive control: their source text has no "в сутки" qualifier, matching the structured field's own silence on time basis exactly).
10. **Source defect 5688**: **QUOTE_FOUND_NORMALIZED_MATCH** — real evidence exists; root cause was a PDF hyphen-linewrap ("бета-\nлактамные") colliding with whitespace normalization, not a data defect.
11. **Source defect 6052**: same root cause and fix as 5688 (identical quote, same PDF/page).

## 12-20. Pool counts

12. Exact-link count before repair: 74.
13. Exact-link count after repair (engine alone): 47.
14. Exact links downgraded: 27 (`COMPATIBLE_BASIS_UNSPECIFIED`).
15. Exact links rejected: 0 directly from the exact-link bucket (the 4 rejections came from the single-candidate bucket).
16. Single candidates: 43 → 39 retained + 4 rejected (`WRONG_RANGE_ANCHOR`, genuine `INCOMPATIBLE_WEIGHT_BASIS`) + 0 promoted to exact.
17. Unit-basis queue size: 43.
18. Source-defect queue size: 0 (both known defects fixed).
19. Table queue size: 8.
20. Engine-review queue size: 11 (engine says exact post-repair, independent Pass A flagged an unrelated structural concern).

## 21-26. Experimental artifacts and final queues

21. **V4/V5 status**: V4 unchanged (2675 rows, 0 approved). V5 (C6.7's 53-record independent-audit-retained artifact) audited and found to contain 17 rows now known basis-invalid — marked `SUPERSEDED_EXPERIMENTAL_ARTIFACT`, kept on disk.
22. **V6 status**: built from the final 36-record intersection (C6.7 independent Pass A retained ∩ C6.8 basis-repaired retained).
23. **V6 populated rows**: 36.
24. **Unrelated changes**: 0, independently diffed across all core + evidence columns, V5→V6.
25. **Owner exact-link queue size**: 36 (`RC030_C68_EXACT_LINK_OWNER_QUEUE.json`).
26. **Taxonomy decision**: no change applied. Existing `REMAINS_AMBIGUOUS`/`WRONG_DOSE_ANCHOR`/`CORRECT_RANGE_DAILY`/`CORRECT_RANGE_SINGLE` verdicts are sufficient for dose-basis review; confirmed and extended C6.7's own prior conclusion.

## 27-34. Tests

27. Targeted tests: 49 (dose-unit-signature matrix) + 3 (pdf_evidence hyphen fix) + 8 (C5 mode extension executions) = 60 new targeted tests.
28. Sandbox tests: `tests/dose_verification_sandbox` — all passing, including the rewritten fix-proof tests (was characterization-only in C6.7).
29. Normalizer tests: unit-canonicalization equivalence re-verified sound; no `medical_normalizer` file changes this pass (the fix lives in `dose_verification_sandbox`, which owns the comparison logic).
30. C4 tests: unchanged, still passing as part of the canonical run.
31. C5 tests: **37/37 passing** (was 31/31 before C6.8), 0 regressions.
32. Canonical collection: unchanged path set (C6.8 added no new canonical-testpath files beyond what C6.7 already added).
33. Canonical pytest: **1506/1506 passing, 1 skipped, 1 xfailed, 0 failed** — identical count to the C6.7 baseline (C6.8's new tests live under `tests/dose_verification_sandbox`, outside canonical testpaths, matching the existing project convention).
34. Fresh-clone result: clean. All 4 commits present in order; sandbox+interface+isolation suite 409 passed/4 skipped; canonical suite 1496 passed/11 skipped/1 xfailed (skip-count difference vs. the main checkout is expected — gitignored `*.sqlite`/`*.db` corpus files aren't present in a bare clone, triggering the suite's existing optional-corpus skip guards).

## 35-45. Final state

35. DB hashes: `assembled_regimens.sqlite` = `9f505d08...`, `review_workbench_p56.sqlite` = `3e479ee7...`, `kb_final.db` = `16c31fba...` — **identical to the C6.7 baseline**, re-verified after every commit.
36. Eligible count: **0/2675**, unchanged.
37. Approved count: **0**, unchanged, re-verified directly.
38. Threshold state: `TYPES_MEETING_PRECISION_THRESHOLD = set()`, unchanged, not referenced anywhere in the new code.
39. Review DB state: **9153/9153 review_tasks PENDING, 0 review_decisions** — unchanged.
40. Clinical Engine state: **disconnected**, re-verified directly (0 `review_workbench` imports in engine core), the C6.7-added automated gate (50 tests) still passing.
41. Authoritative migration state: **not authorized, not executed** — no authoritative row modified; V6 is a separate, gitignored, experimental SQLite copy.
42. Push status: **not pushed** — 28 commits ahead of `origin/main` (was 24 at C6.8 start), 0 behind.
43. Remaining owner decisions: confirm/reject 36 exact-link records, review 15 general single-candidate, 43 unit-basis-ambiguous, 8 table-derived (pending tooling), 11 engine/Pass-A-disagreement records.
44. Remaining physician decisions: **none** — every open question remains a source-fidelity question, not a clinical-appropriateness question.
45. Exact blockers to C7 / P6: same as C6.7 — 9153 PENDING review tasks with 0 registered reviewers, 0 owner review events for any newly-queued record, `calculation_eligibility = BLOCKED` unconditionally, `TYPES_MEETING_PRECISION_THRESHOLD` empty, Clinical Engine structurally disconnected (now with an automated gate). **P6 remains BLOCKED.**

## Final verdict

**B) C6.8 COMPLETE — EXACT-LINK POOL REDUCED AFTER BASIS-CORRECT REPLAY**

The dose-basis defect is fixed and regression-tested (60 new tests, 2 genuine positive controls proving the fix discriminates on real evidence rather than blanket-downgrading). The exact-link pool is smaller and more trustworthy than at any prior checkpoint: 74 (C6.5/C6.6, uncorrected) → 53 (C6.7, independent-audit-only) → 36 (C6.8, independent-audit ∩ basis-repair). Both known source-quote defects were resolved as false alarms (a matching bug, not a data defect) rather than left open. No authoritative data was touched; no calculation was activated; no push was made; P6 remains blocked.
