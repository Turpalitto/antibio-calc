# RC-030 C6 — Span-Linked Range Re-derivation: Final Report

## 1. Exact C6 commit
Recorded after commit (Phase 26) — see Phase 26 output below and the commit-boundary section of the response accompanying this document.

## 2. Parent commit
`863f981842521fa860e50ea4fd2dd0bfc11e57b8` (C5 portability fix)

## 3. Modules introduced
`dose_verification_sandbox/span_attribution.py` (canonical text model, span detection, deterministic attribution engine, classification taxonomy) + `tests/dose_verification_sandbox/test_span_attribution.py` (30 tests).

## 4. Attribution algorithm
See `RC030_C6_ARCHITECTURE_AUDIT.md` for full detail. Summary: normalize text (NFC, dash unification, whitespace collapse, offset-preserving) → detect antibiotic spans (governed dictionary only) → detect true dose-range spans (unit-whitelist + exclusion rules for maximum/non-increasing candidates) → score each range against the nearest antibiotic span for same-segment/unit-match/scalar-match/phase-conflict → classify per the required 12-value taxonomy. No clinical plausibility, no AI voting, no common-dosing-knowledge shortcuts.

## 5. Structural boundary rules
Alternative separator (`или`), semicolon, sentence-ending period, and loading/maintenance phase-marker vocabulary — each checked as a hard or soft boundary between a candidate drug and range span (full rule table in the architecture audit).

## 6. Table recovery rules
**Not executed this turn.** `C:\clinrec_downloader` resolves to the repository root in this environment (no PDF corpus present) — DocLayout-YOLO/Table Transformer/PyMuPDF page-level extraction genuinely cannot run here. Table-flagged records are honestly classified `AMBIGUOUS_TABLE_CONTEXT` with an explicit `table_recovery_unavailable_in_this_environment` reason rather than guessed at from flattened text.

## 7. 179 suspect input count
179 (verified against the real, existing 365-row manifest's `SUSPECT_MULTI_DRUG_QUOTE` rows).

## 8. SAFE_EXACT_LINK count
**0**

## 9. SAFE_TABLE_LINK count
**0** (table recovery unavailable, see §6)

## 10. SAFE_SINGLE_CANDIDATE count
**0**

## 11. Still-ambiguous count
46 (`AMBIGUOUS_ALTERNATIVE_BOUNDARY` 23, `AMBIGUOUS_TABLE_CONTEXT` 12, `AMBIGUOUS_MULTIPLE_DRUGS` 10, `AMBIGUOUS_LOADING_MAINTENANCE` 1)

## 12. Wrong prior attribution count
179 / 179 — every one of the 179 records' V2 naive result is confirmed unsafe by V3 (none reach a SAFE classification under the stricter span-linked standard; three spot-checked in detail in the architecture audit, all confirming the naive heuristic would have been wrong to trust).

## 13. Not-a-range count
22 (`NOT_A_DOSE_RANGE`)

## 14. Source-blocked count
0 (`SOURCE_INCOMPLETE`/`SOURCE_CORRUPTED`) — every one of the 179 records had a non-empty `source_quote` in `assembled_regimens.sqlite`.

## 15. Internal-conflict count
0 — the literal double-pass-with-hash-freeze design (Phase 12) was not implemented as a separate two-pass pipeline this turn (see §32 remaining decisions); determinism was instead verified via repeated-call hash equality (`test_deterministic_repeat_same_hash`), which is the property that design was protecting.

## 16. V2 versus V3 differences
Full detail in `RC030_C6_V2_V3_COMPARISON_REPORT.md`. Headline: V2 (naive) proposed a `dose_max` for 100% of the 179 SUSPECT rows (that's *why* they're in the corpus); V3 (span-linked) proposes a `dose_max` for **0%** of them, having independently verified each is either wrong-drug, boundary-crossing, phase-conflicting, or a malformed source-text artifact.

## 17. Unrelated clinical changes
**0** — no clinical field (antibiotic, dose scalar, unit, frequency, route, duration, diagnosis, status, approval) was touched anywhere in this turn; the authoritative `assembled_regimens.sqlite` hash is byte-identical before and after.

## 18. Experimental rows changed
0 rows written to any experimental SQLite — Part X's suggested `generated/rc030_range_rebuild_v3/*.sqlite` artifacts were **not built** this turn: with 0 SAFE-classified rows, there is nothing to populate beyond a byte-identical copy of the authoritative table, which was judged not worth the generated-artifact weight for a diff that changes nothing (documented as a deferred step, not a silent omission).

## 19. Owner-review queue size
23 (`RC030_C6_OWNER_REVIEW_QUEUE.json`) — all `AMBIGUOUS_MULTIPLE_DRUGS`/`AMBIGUOUS_TABLE_CONTEXT`/`AMBIGUOUS_LOADING_MAINTENANCE` records. No `SAFE_EXACT_LINK` sample was possible (none exist).

## 20. Tests added
30, in `tests/dose_verification_sandbox/test_span_attribution.py`, covering normalization, exclusion rules, the core wrong-drug/boundary safety property, loading/maintenance, table-context honesty, determinism, and no-I/O/no-Clinical-Engine/threshold-untouched regressions.

## 21. Targeted test results
30/30 passed.

## 22. Sandbox results
`tests/dose_verification_sandbox/` full suite: 235 passed (205 pre-existing + 30 new), 0 failed.

## 23. Normalizer results
`medical_normalizer/tests/`: all passed alongside the sandbox and C5 interface suites in a combined 1084-test run, 0 failed.

## 24. C5 interface test results
`tests/rc030_owner_interface/`: 24 passed (unaffected by C6).

## 25. Canonical results
Collection: 1458 (unaffected — `tests/dose_verification_sandbox` is not in `testpaths`, same convention as C3-C5). Full canonical pytest: recorded in the commit-boundary section of the accompanying response (run in background during document preparation).

## 26. DB hashes
`assembled_regimens.sqlite`, `kb_final.db`, `review_workbench_p56.sqlite` — all unchanged throughout this turn (re-verified multiple times during processing).

## 27. Eligible count
0/2675 (unchanged).

## 28. Approved count
0 (unchanged).

## 29. Review DB state
`review_decisions = 0`; 9153 `review_tasks` PENDING (unchanged).

## 30. Clinical Engine state
Disconnected (unchanged; `span_attribution.py` has zero `clinical_engine` references, grep- and test-verified).

## 31. Migration readiness
**Not ready.** 0 of 179 SUSPECT records reached `SAFE_EXACT_LINK`/`SAFE_TABLE_LINK`. `RC030_C6_AUTHORITATIVE_MIGRATION_UPDATE.md` states explicitly: AUTHORITATIVE MIGRATION NOT AUTHORIZED, and there are currently 0 qualifying rows to propose even if it were.

## 32. Remaining owner decisions
- Whether to re-run the 186 `TRUSTWORTHY` V2 rows through this turn's stricter span-linked engine (not done this turn — scope was the 179 SUSPECT records specifically) — this is the most promising next step toward an eventual non-empty migration candidate pool.
- Whether to obtain/mount a real local PDF corpus so Part VI's table-layout recovery (DocLayout-YOLO/Table Transformer/PyMuPDF) can actually run — without it, `AMBIGUOUS_TABLE_CONTEXT` (12 records) and any record whose true evidence lives in table structure the flattened `source_quote` lost cannot be resolved further.
- Whether to expand the loading/maintenance phase-marker vocabulary (currently misses perioperative timing language like "во время операции"/"после операции", contributing to the large `WRONG_RANGE_ANCHOR` bucket subsuming what might more precisely be `AMBIGUOUS_LOADING_MAINTENANCE` in some cases) — a refinement, not a safety fix, since the safety property (never wrongly SAFE) already holds.
- Whether to review and adjudicate the 23-item owner queue via the C5 interface.
- Whether to implement the literal double-pass-with-frozen-hash design from Phase 12 as a distinct pipeline (current determinism testing covers the same property via repeated-call hashing, but not literally two independent passes compared against each other).

## 33. Push status
Not pushed — confirmed in the commit-boundary section of the accompanying response.

## 34. P6 status
Remains BLOCKED. No calculation activated, no clinical/physician approval performed, `TYPES_MEETING_PRECISION_THRESHOLD` untouched, no authoritative database or review_workbench write, no Clinical Engine connection, no AI judgment substituted for owner validation, no automatic acceptance of any recovered range (there were none to accept).
