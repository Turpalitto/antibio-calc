# RC-030 Validation Sample — Design

Deterministic stratified sample (`seed=20260716`) drawn live from the current `assembled_regimens.sqlite` (SHA-256 `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9`) and the current `semantics_parser.py` (SHA-256 `78932988d61670744523f6879f34a35706a9ca3b22193dd5e469d2e3b217277f`). Sampling itself is mechanical row selection — it makes no fidelity judgment about any record and does not require clinical review to construct.

## Quota vs. achieved

| Stratum | Requested | Available | Achieved |
|---|---|---|---|
| WEIGHT_PER_DAY | 60 | 446 | 60 |
| WEIGHT_PER_DOSE | 60 | 80 | 60 |
| FIXED_PER_DAY | 40 | 506 | 40 |
| FIXED_PER_DOSE | 40 | 579 | 40 |
| RANGE_PER_DAY | 30 | **0** | **0** |
| RANGE_PER_DOSE | 30 | **0** | **0** |
| AMBIGUOUS control | 30 | 236 | 30 |
| UNPARSED control | 20 | 74 | 20 |
| Max-dose candidates (all) | — | 104 | 104 |
| Multi-alternative high-risk | 30 (cap) | 820 | 30 |
| Pediatric high-risk | 30 (cap) | 868 | 30 |
| Sub-daily frequency (<1/day) | 30 (cap) | 85 | 30 |
| Loading/maintenance | 30 (cap) | 7 | 7 |
| Longest quotes | 20 | 20 | 20 |
| Shortest quotes | 20 | 20 | 20 |
| Multi-numeric-dose (≥4 numbers in quote) | 30 (cap) | 1,614 | 30 |

**Honest gap:** `RANGE_PER_DAY`/`RANGE_PER_DOSE` are defined semantic types in `semantics_models.SEMANTIC_TYPES` and reachable in `semantics_parser.classify_regimen()`'s code path, but **zero rows in the current corpus classify into either type** — `is_range` never evaluates true against the real 2,675-row corpus. This is reported as-is rather than backfilled with a substitute stratum; a real range-dose row (e.g. "10–15 mg/kg/day") may exist in the corpus but not be recognized as a range by the parser's current numeric-range detection, which is itself worth a follow-up parser investigation, separate from sample design.

## Sample size

**488 unique regimens** after de-duplication across overlapping strata (a single row can satisfy, e.g., both `WEIGHT_PER_DAY` and `PEDIATRIC_HIGH_RISK`) — within the mission's 300–400 target range in spirit, somewhat above it because several strata (max-dose, high-risk categories) were sampled independently on top of the core six type-strata rather than drawn exclusively from within them.

## Output

`RC030_VALIDATION_SAMPLE_MANIFEST.json` — a generated review artifact (regimen IDs + assigned strata only, no clinical content), explicitly **not staged**, pending artifact classification in a later commit per the mission's Phase 10 instruction.

## What this sample is *not*

This manifest identifies **which** rows a human reviewer should look at next. It contains no fidelity verdicts, no precision numbers, and no evidence packets. Phases 11 (evidence packet generation), 14 (human fidelity review), and 15 (precision calculation) are separate, unstarted work — see the final verdict in this turn's response for why they were not attempted here.
