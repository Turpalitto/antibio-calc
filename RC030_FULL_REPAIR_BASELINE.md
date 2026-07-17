# RC-030 Full Repair — Baseline Freeze

Recorded 2026-07-16 before any Part II+ code change. Machine copy: `RC030_FULL_REPAIR_BASELINE.json`.

- HEAD: `394818675b0ed199e03cae1d89e38a488f5102ce`, branch `main`
- Source DB hashes: `assembled_regimens.sqlite` `9f505d08…`; `normalized_regimens.sqlite` `c7b67354…`
- Review DB hash: `review_workbench_p56.sqlite` `3e479ee7…`; `review_decisions` = 0; 9,153 tasks `PENDING`
- Parser (`semantics_parser.py`) sha256 first16: `78932988d6167074`
- Normalizer (`drug_parser.py`) sha256 first16: `3c13312e46193123`
- Assembled rows: **2,675**; normalized rows: 2,675
- Semantic distribution (old parser): MISSING 658, FIXED_PER_DOSE 579, FIXED_PER_DAY 506, WEIGHT_PER_DAY 446, AMBIGUOUS 236, NOT_APPLICABLE 96, WEIGHT_PER_DOSE 80, UNPARSED 74
- Range-candidate rows (source_quote holds `N-M unit`): **348**
- Max-dose candidates: 104
- Calculation-eligible: **0 / 2,675**; approved objects: 0; `TYPES_MEETING_PRECISION_THRESHOLD` = `set()`
- Owner events: 1 (regimen 6657); AI-audit events: 60; Clinical Engine: disconnected

## Required baseline check
- assembled rows = 2,675 ✅
- calculation eligible = 0 ✅
- approved objects = 0 ✅
- review decisions = 0, all tasks PENDING ✅
- Clinical Engine disconnected ✅

Authoritative DB hashes were re-read after baseline collection and are unchanged.
