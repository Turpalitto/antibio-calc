# RC-030 P5.6 C6.7 — Safe Range Candidate Verification, Commit-Boundary Audit, Owner Review Package, and C7 Entry Preparation — Final Report

## 1-4. HEAD / commits / boundary conclusion

1. Starting HEAD: `8b9ba872f180bb23eeda68e9c7f9a355d3f92dff` (matched expected).
2. Final HEAD: `a01c9bf` (after 4 new commits).
3. Commits created (in order, no amend, no rebase, no force-push, no push):
   - `c27febe` — C6.7-A: baseline freeze, commit-boundary audit, independent verification tooling and results, Clinical Engine isolation test.
   - `ed4c87c` — C6.7-B: unit-basis conflation characterization and adversarial regression tests.
   - `2f80d2c` — C6.7-C: C5 `range-exact-review`/`range-single-review` modes, two owner-review queues.
   - `a01c9bf` — C7-ENTRY: owner workload, precision policy, sample-size proposals, entry decision.
4. Combined-commit boundary conclusion (for `6045eea`): **BOUNDARY_ACCEPTABLE_WITH_DOCUMENTED_COUPLING** — no safety-relevant coupling (no DB writes, no Clinical Engine import, no threshold mutation, per-file rollback mechanical), but the requested five-separate-commits granularity was not honored; documented, not retroactively fixed.

## 5-11. Candidate pool and disposition counts

5. Candidate total: **117** (74 + 43, confirmed exact, 0 duplicates).
6. Exact-link initial count: **74**.
7. Single-candidate initial count: **43**.
8. Exact links retained: **53** (`EXACT_LINK_RETAINED`).
9. Exact links downgraded: **18** (13 `EXACT_LINK_DOWNGRADED_AMBIGUOUS` + 5 `EXACT_LINK_DOWNGRADED_TABLE_REQUIRED`).
10. Exact links rejected: **2** (`EXACT_LINK_REJECTED_WRONG_ANCHOR`); plus 1 `EXACT_LINK_ENGINE_REVIEW_REQUIRED` (6085, low-severity unit-annotation gap, not fully retained nor rejected).
11. Single candidates by disposition: 26 `SINGLE_REQUIRES_SIMPLE_OWNER_CONFIRMATION`, 8 `SINGLE_REQUIRES_TABLE_REVIEW`, 2 `SINGLE_SOURCE_BLOCKED`, 2 `SINGLE_NOT_A_RANGE`, 2 `SINGLE_REQUIRES_ALTERNATIVE_REVIEW`, 2 `SINGLE_WRONG_ANCHOR`, 1 `SINGLE_REQUIRES_PHASE_SPLIT`, 0 `SINGLE_DICTIONARY_CONFIRMATION`.

## 12-19. Evidence audits

12. PDF validation result: 39/39 unique source PDFs byte-hash clean against `CORPUS_MANIFEST.json`. Page/quote check: 115/117 clean, 2 `PDF_QUOTE_NOT_FOUND` (5688, 6052 — quote not present anywhere in the cited 75-page document, a genuine source-attribution defect).
13. Table evidence result: 0/117 candidates carry the engine's own table flag, but independent Pass A identified 13 as flattened table rows the engine missed (5 in the excluded exact-link set, 8 in Queue B) — no table-layout ML tooling available in this environment, so these remain unreviewable pending that tooling.
14. Unit-normalization audit: script-canonicalization fix (mg↔мг etc.) confirmed sound; found a real, pre-existing, unrelated defect — `_base_unit()` cannot distinguish absolute mg from per-kilogram mg/kg from per-kilogram-per-day mg/kg/day, affecting 14/117 records (6 high-severity in the exact-link pool). Characterized and regression-tested, not fixed (fix requires its own commit per the owner's constraints).
15. Adversarial regression result: 4 new characterization tests added and passing; existing adversarial suite in `test_span_attribution.py` (already extensive, ~20+ cases) re-run clean, 0 regressions.
16. Independent Pass A agreement: 54/117 `EXACT_AGREEMENT`, 30/117 `DIRECTIONAL_AGREEMENT`, 13 `TABLE_REQUIRED`, 13 `ENGINE_OVERCONFIDENT`, 7 `WRONG_ENGINE_LINK` — full breakdown in `RC030_C67_DOUBLE_PASS_REPORT.md`.
17. Engine disagreement count: 7 genuine `WRONG_ENGINE_LINK` cases (2 exact-link, 5 single-candidate), each individually investigated and explained (not forced to agree).
18. V4 rows: 2675 total, 74 with populated range fields, 0 unrelated changes vs. authoritative DB, 0 approved — re-verified independently, not taken on faith.
19. V5 rows: 2675 total, **53** with populated range fields (only `EXACT_LINK_RETAINED`), 0 unrelated changes vs. V4, 0 approved. V5 was created (not the no-retained-rows case).

## 20-27. Owner package and policy

20. Unrelated DB changes: **0** (V4→V5 diff, all core + evidence columns, independently checked).
21. Exact-link owner queue size: **53** (Queue A).
22. Single-candidate owner queue size: **43** (Queue B, all of them, grouped by reason).
23. C5 compatibility: gap found (no `range-exact-review`/`range-single-review` modes existed) and fixed — 2 new modes added to `build_interface.py` and `owner_review_template.html`, 5 new tests, 31/31 C5 tests passing.
24. AI pre-review status: built as a separate, non-owner-facing companion file (`generated/rc030_c67/ai_pre_review_companion.json`, 96 records, `review_origin=AI_PRE_REVIEW`, `owner_verified=false`) — never merged into either queue; local-only, not committed (matches the owner's prohibition on committing AI events as owner truth).
25. Owner workload: ~240 minutes estimated for the 83 non-table, non-excluded records across both queues; 13 table cases deferred pending tooling; 21 non-retained exact-link records currently have no queue at all (flagged as an open architecture decision).
26. Precision metric policy: `OWNER_SOURCE_FIDELITY_PRECISION` defined against the existing (unchanged) `CONFIRMING_VERDICTS`/`ERROR_VERDICTS` taxonomy; Queue A and Queue B scored separately; explicit statement that this measures source fidelity, not clinical dosing accuracy.
27. Sample-size proposals: Wilson lower-bound table for N=20/30/50/53/74 at 0-3 errors provided; no threshold selected (owner's decision).

## 28-45. Test/state/gate summary

28. C7 entry status: **READY_FOR_OWNER_REVIEW**.
29. Targeted tests: 4 new unit-basis adversarial tests (`test_c67_unit_basis_adversarial.py`), 5 new C5 mode tests, 50 new Clinical Engine isolation tests (`test_review_workbench_isolation.py`) — **59 new tests, all passing**.
30. Sandbox tests: `tests/dose_verification_sandbox` + `tests/rc030_owner_interface` — 300/300 passing (was 293 before this program).
31. Normalizer tests: unit-canonicalization behavior verified directly (script equivalence sound, denominator-shape gap characterized); no dedicated `medical_normalizer` test file changes this pass.
32. C4 tests: `test_c4_governance_hardening.py` — unchanged, still 41/41 passing (verified as part of the full canonical run).
33. C5 tests: 31/31 passing (26 pre-existing + 5 new).
34. Canonical collection: unchanged path set, +50 new tests from `clinical_engine/tests/test_review_workbench_isolation.py`.
35. Canonical pytest: **1506 passed, 1 skipped, 1 xfailed, 0 failed** (was 1456/1/1/0 before this program).
36. DB hashes: `assembled_regimens.sqlite` = `9f505d08...`, `review_workbench_p56.sqlite` = `3e479ee7...`, `kb_final.db` = `16c31fba...` — **all three identical to the Phase 0 baseline**, re-verified after every commit.
37. Eligible count: **0/2675**, unchanged.
38. Approved count: **0**, unchanged (re-verified directly against the live DB, not inferred).
39. Review DB state: **9153/9153 review_tasks PENDING, 0 review_decisions, 0 review_events, 0 review_assignments** — unchanged.
40. Clinical Engine state: **disconnected**, re-verified directly (zero `review_workbench` import in `engine.py`/`pipeline.py`/`readers/`/`api/`), and this claim now has a real automated gate (50 new tests) where previously it rested only on repeated manual grep in report prose.
41. Threshold state: `TYPES_MEETING_PRECISION_THRESHOLD = set()` — unchanged, not referenced by any code touched this pass.
42. Authoritative migration state: **not authorized, not executed** — no row in `assembled_regimens.sqlite` was modified; V5 is a separate, gitignored, experimental SQLite copy under `generated/rc030_range_rebuild_v5/`.
43. Push status: **not pushed** — local is now 23 commits ahead of `origin/main` (was 19), 0 behind.
44. Remaining owner decisions: confirm/reject 53 Queue A records, review 43 Queue B records (26 simple, 8 pending table tooling, 2 alternative-basis, 2 wrong-anchor, 2 not-a-range, 2 source-blocked/needs re-sourcing, 1 phase-split), plus the open architecture question of what queue (if any) the 21 non-retained exact-link records go into.
45. Remaining physician decisions: **none identified** — every open question in this pool is a source-fidelity question (does the record match its cited source), not a clinical-appropriateness question.

## 46. Exact P6 blockers

- 9153 review_tasks remain PENDING with 0 reviewers registered (per `P56_GOVERNANCE_HARDENING_CLOSURE_REPORT.md`, unchanged by this program).
- 0 owner review events exist for any of the 96 newly-queued records — Queue A/B are inputs, not decisions.
- `calculation_eligibility = BLOCKED` for all 2675 assembled regimens, unconditionally.
- `TYPES_MEETING_PRECISION_THRESHOLD` remains empty.
- Clinical Engine remains structurally disconnected from RC-030 review governance (now with an automated gate).
- **P6 remains BLOCKED.**

## Final verdict

**B) EXACT-LINK POOL REDUCED — OWNER REVIEW PACKAGE READY**

The independently-audited exact-link pool shrank from 74 to 53 (72% retained) after two convergent, independent verification methods (deterministic re-run + blinded reviewer re-attribution + byte-level PDF/unit audits) found real, evidence-cited reasons to downgrade or reject 21 records — not because a target count was being protected, but because it wasn't. Both governed owner-review queues (53 + 43) are built, hashed, free of preloaded verdicts, and the C5 interface now has the two dedicated modes the spec required. No authoritative data was touched; no calculation was activated; no push was made; P6 remains blocked.
