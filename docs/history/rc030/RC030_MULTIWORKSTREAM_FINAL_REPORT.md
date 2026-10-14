# RC-030 Multi-Workstream Program — Final Report

## 1. Exact starting HEAD
`7530b4796b924b17857b3ef7e52bb32e900d0501` (C6.1 final report)

## 2. Exact final HEAD
`2b04e80c26f9dcd0f85268a425d7b9ae82e2478a` (C7-PREP)

## 3. All commits created
- `6045eea3a4ec68c7bf2cfa9a31d0306f44a4fcae` — C6.2-C6.6 combined (dictionary/PDF discovery/enhanced replay/structural analysis/owner queue + C5 compatibility)
- `2b04e80c26f9dcd0f85268a425d7b9ae82e2478a` — C7-PREP (entry criteria, precision simulation, validation plan, gate matrix)

## 4. Exact commit parent chain
`2b04e80` → `6045eea` → `7530b47` (C6.1 report) → `549016c` (C6.1 main) → `6e27ceb` (C6) → `863f981` (C5 fix) → `ed5d863` (C5) → `c41efb5` (C4) → `d79bb3c` (C3) → `35d432e` (C2) → `aa75331` (C1) → base

## 5. Dictionary gaps before/after
40 before. After bounded context-expansion (real PDF page text, whitespace-tolerant matching): 6 remain genuinely dictionary-limited; 34 resolved to more accurate labels once the drug name (present nearby on the real page) became visible.

## 6. Deterministic dictionary additions
**0.** The root cause of most `DICTIONARY_GAP` records was quote truncation (drug name outside the stored `source_quote` window), not missing dictionary entries — the relevant drugs (Цефтриаксон, Ко-тримоксазол, Цефотаксим, etc.) were mostly already governed.

## 7. Dictionary additions rejected
N/A — none were proposed, since none were needed.

## 8. PDF corpus coverage
**365/365 (100%)** of range-candidate PDFs found. Major correction to C6's prior "no PDF corpus" finding — `C:\clinrec_downloader` is a real, separate project directory containing the actual corpus.

## 9. PDF hash matches
**365/365 (100%)** against `CORPUS_MANIFEST.json`'s recorded expected SHA-256.

## 10. PDF hash mismatches
0.

## 11. Missing PDFs
0.

## 12. Table records recovered
**0** via true bbox/row/column reconstruction (the six-tool ML stack was not run this turn — explicit scope decision, not a data-availability blocker anymore). 23 `AMBIGUOUS_TABLE_CONTEXT` records remain exactly as classified in C6.1.

## 13. Table records still ambiguous
23 (unchanged).

## 14. SAFE_EXACT_LINK after enhanced evidence
**74** (up from 0 in C6.1) — driven by the unit-normalization fix, not table recovery.

## 15. SAFE_TABLE_LINK after enhanced evidence
0.

## 16. SAFE_SINGLE_CANDIDATE
**43** (up from 0).

## 17. Wrong-anchor count
60 (down from 223).

## 18. Not-a-range count
26 (down from 26 — effectively unchanged, 1 shifted elsewhere in intermediate testing but final count matches).

## 19. Alternative-boundary count
40 (down from 48).

## 20. Loading/maintenance count
2 range-candidate records (unchanged); 80/2675 broader corpus rows carry phase-marker vocabulary (new finding, mostly scalar doses outside this program's range-candidate scope).

## 21. Split proposals
0 — Phase 17 (regimen-splitting proposals) was not executed this turn; deferred, noted as a candidate for a future turn given the volume of `AMBIGUOUS_ALTERNATIVE_BOUNDARY`/`AMBIGUOUS_MULTIPLE_DRUGS` records (90 combined) that could benefit from it.

## 22. V4 artifact status
**Built.** `generated/rc030_range_rebuild_v4/assembled_regimens_range_v4.sqlite` (excluded from git per policy).

## 23. V4 changed rows
74 rows received `dose_min`/`dose_max`/`dose_is_range`/`range_provenance` (the `SAFE_EXACT_LINK` set); 43 rows received `range_provenance` metadata only (`SAFE_SINGLE_CANDIDATE`, no dose fields per the mission's explicit rule).

## 24. Unrelated changes
**0** — all 10 core clinical fields verified byte-identical between the original and V4 copy across all 2675 rows.

## 25. Owner-review queue size
123 items (`RC030_C66_OWNER_REVIEW_QUEUE.json`).

## 26. C5 range-review compatibility
**Verified with zero core modification.** A 66-record C5-compatible bundle built from the queue was successfully processed by the existing, unmodified `build_interface.py`.

## 27. AI pre-review status
Not performed this turn.

## 28. C7 entry conditions
13 defined; 5 unambiguously unmet (all require real owner review activity not performed this turn); 6 met at the code/infrastructure level; 2 partial.

## 29. Precision simulation result
17/17 synthetic scenarios pass; `TYPES_MEETING_PRECISION_THRESHOLD` confirmed `set()` after every scenario, including the most favorable (100% precision, N=30). One pre-existing architectural gap (supersession-chain resolution) documented via an explicit test rather than left as a silent surprise.

## 30. Threshold state
`set()` — unchanged throughout the entire program.

## 31. Targeted tests
C6.2-C6.6: 12 new tests (2 in `test_span_attribution.py` + 10 in new `test_pdf_evidence.py`), 37+10=47 total in those two files. C7-PREP: 17 new tests. **29 new tests this turn, 64 total across the two new/extended files.**

## 32. Sandbox tests
Full `tests/dose_verification_sandbox/` suite: passing in both working tree and fresh clone (fresh clone: relevant subset 1114 passed + 4 optional skips across the combined sandbox/interface/normalizer run).

## 33. Normalizer tests
Passing (part of the combined 1118-test working-tree run / 1114+4-skip fresh-clone run).

## 34. C5 tests
Passing, unaffected (`tests/rc030_owner_interface/`).

## 35. Canonical collection
1458 (unchanged in both working tree and fresh clone).

## 36. Canonical pytest
1457 passed, 1 xfailed, 0 failed (413s, run after the C6.2-C6.6 commit; unaffected by the subsequent C7-PREP-only test addition since `tests/dose_verification_sandbox` remains outside `testpaths`).

## 37. Fresh-clone results
Both commits verified in a single fresh clone: HEAD/parent chain intact back through C1, 20 total files changed across the two commits, clean status, deterministic replay against the real external DB reproduced `SAFE_EXACT_LINK` for regimen 5671 exactly, all safety invariants held.

## 38. Authoritative DB hashes
`assembled_regimens.sqlite` `9f505d08...`, `kb_final.db` `16c31fba...`, `review_workbench_p56.sqlite` `3e479ee7...` — all unchanged throughout, re-verified at every checkpoint including inside the fresh clone.

## 39. Eligible count
0/2675 (unchanged).

## 40. Approved count
0 (unchanged).

## 41. Review DB state
`review_decisions = 0`; 9153 `review_tasks` PENDING (unchanged).

## 42. Clinical Engine state
Disconnected throughout (re-verified every checkpoint).

## 43. Push status
Not pushed — 18 commits ahead of `origin/main`.

## 44. Authoritative migration status
**NOT AUTHORIZED, NOT EXECUTED.** 117 candidate rows now exist (up from 0) but none were written to any authoritative table; `AUTHORITATIVE_MIGRATION_ALLOWED = false` is a static field on every single record regardless of classification.

## 45. Remaining owner decisions
- Review the 15-item `SAFE_EXACT_LINK` sample in the owner queue via the C5-verified-compatible interface (highest-value next step).
- Decide whether to invest in the six-tool table-layout ML stack for the 23 `AMBIGUOUS_TABLE_CONTEXT` records, now that the PDF corpus is confirmed available.
- Decide whether to pursue the age-group-aware disambiguation enhancement identified in C6.4 (concrete, well-evidenced, not yet implemented).
- Ratify a governance minimum sample size and confidence-bound method (`RC030_C7_OWNER_VALIDATION_PLAN.md` proposes Wilson lower bound + N≥30, neither is approved).
- Decide whether to pursue Phase 17 regimen-splitting proposals for the 90 alternative/multi-drug-boundary records.

## 46. Remaining physician decisions
No physician review has occurred anywhere in this program to date; every SAFE-classified record requires eventual physician review before any real clinical use, regardless of owner source-fidelity confirmation.

## 47. Exact blockers to P6
Gates B through J of `RC030_C7_GATE_MATRIX.md` (owner source-fidelity validation, minimum sample, precision threshold, confidence-bound ratification, authoritative migration authorization, adapter/Clinical-Engine integration, end-to-end clinical QA, release approval) — all require real owner and physician review activity that has not occurred and was not authorized this turn. Gate A (source attribution) made real progress (0→117 candidates) but is necessary, not sufficient.

---

## FINAL VERDICT

**B) DICTIONARY AND PDF RECOVERY COMPLETE — MOST RANGE CASES STILL REQUIRE OWNER REVIEW**

248 of 365 records (68%) remain ambiguous, wrong-anchored, dictionary-gap-limited, table-blocked, or not-true-ranges. The 117 that reached a SAFE classification are a genuine, real, evidence-backed improvement (found via two real deterministic engine defects, not a relaxed rule) but every one of them — SAFE or not — remains `NOT_OWNER_VERIFIED`, `NOT_CLINICALLY_APPROVED`, `CALCULATION_BLOCKED`, and `AUTHORITATIVE_MIGRATION_ALLOWED = false`. No calculation was activated, no clinical value was approved, `TYPES_MEETING_PRECISION_THRESHOLD` was never populated, the Clinical Engine was never connected, no authoritative database was modified, and no push occurred. **P6 remains BLOCKED.**
