# RC-030 C6.1 — Complete Range Corpus Revalidation: Final Report

## 1. Exact HEAD
`549016c6b9fc8330eb93b509664db26ee42d8980`

## 2. Parent
`6e27cebbfd5ccce5973ab4ee19e9f62c56d37c64` (C6)

## 3. Code changes
One deterministic engine fix in `dose_verification_sandbox/span_attribution.py`: the zero-antibiotic-span case (a true dose range with no dictionary antibiotic match) is now classified `DICTIONARY_GAP` (new constant) instead of the misleading `AMBIGUOUS_MULTIPLE_DRUGS`. `ENGINE_REVIEW_REQUIRED` was also added as a defined-but-currently-unused constant per the required taxonomy (0 records needed it this turn — the literal Phase 12 double-pass-with-hash-freeze design was not implemented as a separate mechanism; determinism was verified via Pass A hash-freezing before Pass B comparison, per Phase 4/5).

## 4. Replay tooling
No new committed tooling file — the 365-record replay was run via a one-off inline script (not saved to the repository), consistent with "commit only governed replay tooling/tests/docs if repository-worthy" (Phase 18) — the script itself has no reuse value beyond this turn's specific manifest-to-DB join, whereas the *engine* it calls is already committed (C6) and this turn only adds one fix to it.

## 5. Test changes
6 new tests added to `tests/dose_verification_sandbox/test_span_attribution.py` (36 total): the `DICTIONARY_GAP` regression for the exact defect found, a "dictionary gap is never safe" guard, a coincidental-scalar-match-with-multiple-drugs adversarial case, a range-before-antibiotic ordering case, a parenthetical-alternative case, and an aggregate regression covering the real multi-phase/wrong-drug-after-"или" patterns found in the replay.

## 6. Total records
365

## 7. Old TRUSTWORTHY count
186

## 8. Old SUSPECT count
179

## 9. SAFE_EXACT_LINK count
**0**

## 10. SAFE_TABLE_LINK count
**0** (PDF corpus unavailable in this environment)

## 11. SAFE_SINGLE_CANDIDATE count
**0**

## 12. Ambiguity counts
`AMBIGUOUS_ALTERNATIVE_BOUNDARY` 48, `AMBIGUOUS_TABLE_CONTEXT` 23, `AMBIGUOUS_MULTIPLE_DRUGS` 3, `AMBIGUOUS_LOADING_MAINTENANCE` 2 (total ambiguous: 76)

## 13. Wrong-anchor count
223 (`WRONG_RANGE_ANCHOR`)

## 14. Not-a-range count
26 (`NOT_A_DOSE_RANGE`)

## 15. Dictionary-gap count
40 (`DICTIONARY_GAP`)

## 16. Table-blocked count
23 (`AMBIGUOUS_TABLE_CONTEXT`)

## 17. Old trust retained
**0 of 186**

## 18. Old trust revoked
**186 of 186**

## 19. Trust revocation percentage
**100%**

## 20. Owner-review queue size
85 (`RC030_C61_OWNER_REVIEW_QUEUE.json`) — all 40 `DICTIONARY_GAP`, all 23 `AMBIGUOUS_TABLE_CONTEXT`, all 2 `AMBIGUOUS_LOADING_MAINTENANCE`, plus a deterministic sample of 20 former-`TRUSTWORTHY` revoked records.

## 21. Engine defects found
1 — the `DICTIONARY_GAP`/`AMBIGUOUS_MULTIPLE_DRUGS` mislabeling for zero-antibiotic-span cases (found via the Phase 3 dictionary-coverage audit, affecting 40/365 real records).

## 22. Engine defects fixed
1 — fixed with a regression test, before/after replay comparison proving 0 SAFE → 0 SAFE (pure relabeling, no wrong link introduced or removed).

## 23. PDF limitation
Unchanged from C6/baseline: `C:\clinrec_downloader` resolves to the repository root in this environment; no local PDF corpus exists. All 23 `AMBIGUOUS_TABLE_CONTEXT` records and any record whose true evidence requires table-layout recovery remain blocked on this until a real PDF corpus is available.

## 24. Targeted tests
36/36 passed (`test_span_attribution.py`).

## 25. Sandbox tests
`tests/dose_verification_sandbox/` full suite: 241 passed (fresh clone: 237 passed + 4 optional skips), 0 failed.

## 26. Normalizer tests
Passed alongside sandbox/interface suites in the combined 1090-test run (fresh clone: 1086 + 4 skipped), 0 failed.

## 27. C5 tests
`tests/rc030_owner_interface/`: unaffected, passing (part of the combined run above).

## 28. Canonical tests
Collection: 1458 (unchanged). Full canonical pytest: 1457 passed, 1 xfailed, 0 failed (411s).

## 29. DB hashes
`assembled_regimens.sqlite`, `kb_final.db`, `review_workbench_p56.sqlite` — unchanged throughout (re-verified in both working tree and fresh clone, including a live external-DB replay smoke test in the fresh clone).

## 30. Eligible count
0/2675 (unchanged).

## 31. Approved count
0 (unchanged).

## 32. Review DB state
`review_decisions = 0`; 9153 `review_tasks` PENDING (unchanged).

## 33. Clinical Engine state
Disconnected (unchanged; `span_attribution.py` has zero `clinical_engine` references).

## 34. Migration status
**NOT AUTHORIZED, NOT EXECUTED.** `RC030_C61_MIGRATION_READINESS_REPORT.md` formally retires the old `TRUSTWORTHY` label as a migration-readiness signal: 0 of the 186 records it covered survive strict independent re-derivation. The corpus-wide finding (0/365 SAFE) is stronger and more conservative than C6's finding on the 179-subset alone.

## 35. Commit hash
`549016c6b9fc8330eb93b509664db26ee42d8980`

## 36. Push status
Not pushed — 15 commits ahead of `origin/main`.

## 37. Remaining owner decisions
- Whether to pursue dictionary expansion for the 40 `DICTIONARY_GAP` records (most directly actionable path to any future SAFE candidate).
- Whether to obtain a real local PDF corpus to unblock the 23 `AMBIGUOUS_TABLE_CONTEXT` records.
- Whether to adjudicate the 85-item owner review queue via the C5 interface.
- Whether to expand loading/maintenance phase-marker vocabulary (deferred per Phase 18 — no regression-provable improvement attempted this turn beyond the one dictionary-gap fix).
- Whether to formally deprecate/annotate the old `RC030_RANGE_REBUILD_INTEGRITY_REPORT.md`/`RC030_AUTHORITATIVE_RANGE_MIGRATION_PROPOSAL.md` TRUSTWORTHY-based language in light of this turn's finding (not done this turn — those are historical C3 documents, and per the "do not alter historical meaning" precedent established in C3, they are superseded by, not rewritten in light of, this report).

## 38. P6 status
Remains BLOCKED. No calculation activated, no clinical/physician approval performed, `TYPES_MEETING_PRECISION_THRESHOLD` untouched, no authoritative database or review_workbench write, no Clinical Engine connection, no AI judgment substituted for owner validation, no automatic acceptance based on scalar match alone (the opposite — this turn proved scalar match alone is insufficient).

---

## FINAL VERDICT

**B) C6.1 COMPLETE — PREVIOUS TRUSTWORTHY LABEL MOSTLY REVOKED**

(Precisely: 100% revoked, not "mostly" — but this is the closest-fitting of the enumerated verdict options, since option A requires a "strictly safe range candidate set" which does not exist, and option C claims literally zero candidates are safe *without PDF review* specifically, when in fact 342 of the 365 non-safe results are non-safe for reasons unrelated to PDF availability — dictionary gaps, wrong-drug attribution, non-range text. The dominant, corpus-defining finding is the full revocation of the old trust label.)
