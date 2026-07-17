# RC-030 Full Repair — Corpus Impact (2,675 rows)

Three runs: (A) old parser / authoritative scalar corpus, (B) repaired parser / authoritative scalar corpus, (C) repaired parser semantics with the experimental range-preserving artifact carrying both bounds. **Calculation-eligible = 0 in all runs.**

| Semantic type | old (A) | repaired (B) |
|---|---|---|
| AMBIGUOUS | 236 | 740 |
| FIXED_PER_DAY | 506 | 132 |
| FIXED_PER_DOSE | 579 | 670 |
| MISSING | 658 | 658 |
| NOT_APPLICABLE | 96 | 96 |
| UNPARSED | 74 | 74 |
| WEIGHT_PER_DAY | 446 | 211 |
| WEIGHT_PER_DOSE | 80 | 94 |

## Risk-flag distribution (repaired)

| Flag | Count |
|---|---|
| EXPLICIT_DOSE_BASIS_MISSING | 740 |
| SUB_DAILY_FREQUENCY | 82 |
| RANGE_VALUE_COLLAPSED_UPSTREAM | 328 |
| NORMALIZER_RANGE_UPPER_BOUND_DROPPED | 328 |
| WEEKLY_SCHEDULE_UNSUPPORTED | 18 |

## Key deltas

- markerless-now-ambiguous (EXPLICIT_DOSE_BASIS_MISSING): 740
- AMBIGUOUS: 236 → 740 (fail-closed: freq==1 shortcut removed)
- per-dose types (FIXED/WEIGHT/RANGE_PER_DOSE): 659 → 764 (однократно/р.сут/дважды now per-dose)
- weekly schedules: 18
- range-collapsed rows flagged: 328
- sub-daily frequency: 82
- loading/maintenance unresolved: 0
- parser exceptions: 0

**old calc-eligible = 0; repaired calc-eligible = 0. No row became eligible.**