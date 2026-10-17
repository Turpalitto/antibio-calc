# RC-030 / C6.8 Phase 10-12 — Full 365 + 117 Replay Report

## Blinded input freeze

`generated/rc030_c68/pass_a_365_input.json` — 365 records, sha256 `e9a531dac72672dcfa03204b84351316db6f10d4b0a427fbd87f604b352b4d55` (`pass_a_365_input.sha256`). Fields: regimen_id/version, antibiotic, dose, unit, route, frequency, duration_recommended, age_group, diagnosis, source_pdf, source_page, source_quote, needs_review_reasons. No prior classification, engine output, or V4/V5 label included — verified by direct key scan.

## Methodology note: table-context reconstruction

`needs_review_reasons` does not reliably encode whether a record's source is table-derived — verified directly (several records classified `AMBIGUOUS_TABLE_CONTEXT` in the frozen C6.7 result have no "table" substring anywhere in that field, and no other committed table-detection signal exists in the schema). Reusing the frozen C6.7 table-context boolean as an **input reconstruction aid** (not a classification label) is treated as legitimate — it is a structural fact about the source document (is this text a table cell), the same category as reusing `source_pdf`/`page`/`quote`, never a safety verdict. An initial replay pass using a naive `needs_review_reasons`-substring heuristic instead produced 23 spurious classification "changes" that were purely reconstruction artifacts, not engine-repair outcomes — caught and corrected before reporting results below.

## Full 365 replay — classification counts

| Classification | C6.7 (frozen) | C6.8 (repaired engine) | Δ |
|---|---|---|---|
| SAFE_EXACT_LINK | 74 | 47 | -27 |
| SAFE_SINGLE_CANDIDATE | 43 | 66 | +23 |
| WRONG_RANGE_ANCHOR | 60 | 65 | +5 |
| AMBIGUOUS_MULTIPLE_DRUGS | 50 | 49 | -1 |
| AMBIGUOUS_ALTERNATIVE_BOUNDARY | 40 | 40 | 0 |
| AMBIGUOUS_MULTIPLE_RANGES | 7 | 7 | 0 |
| AMBIGUOUS_TABLE_CONTEXT | 23 | 23 | 0 |
| AMBIGUOUS_LOADING_MAINTENANCE | 2 | 2 | 0 |
| DICTIONARY_GAP | 40 | 40 | 0 |
| NOT_A_DOSE_RANGE | 26 | 26 | 0 |
| **Total** | **365** | **365** | |

**32 records changed classification**, all individually traced to a specific, attributable cause:
- **27**: `SAFE_EXACT_LINK` → `SAFE_SINGLE_CANDIDATE` (`COMPATIBLE_BASIS_UNSPECIFIED` — the source text states a dose basis the structured field doesn't, or vice versa; genuinely not equivalent, correctly capped below exact-link).
- **4**: `SAFE_SINGLE_CANDIDATE` → `WRONG_RANGE_ANCHOR` (5514, 5526, 5533, 6072 — genuine `INCOMPATIBLE_WEIGHT_BASIS` rejections).
- **1**: `AMBIGUOUS_MULTIPLE_DRUGS` → `WRONG_RANGE_ANCHOR` (6639 — a multi-drug quote where the repair now correctly identifies the specific cause as a weight-basis conflict rather than a generic multi-drug ambiguity).

No target count was preserved or protected — the pool shrank because the repair is more conservative, not because a number was defended.

## 117-candidate pool reconciliation

| Bucket | Count |
|---|---|
| EXACT_LINK_RETAINED (still SAFE_EXACT_LINK) | 47 |
| EXACT_LINK_DOWNGRADED_UNIT_BASIS (now SAFE_SINGLE_CANDIDATE) | 27 |
| EXACT_LINK_REJECTED_SOURCE / NOT_RANGE | 0 |
| SINGLE_CANDIDATE_RETAINED (still SAFE_SINGLE_CANDIDATE) | 39 |
| SINGLE_REJECTED (now WRONG_RANGE_ANCHOR) | 4 |
| SINGLE_PROMOTED_EXACT | 0 |
| **Total** | **117** |

Zero single-candidates were promoted to exact-link — no rule was relaxed to increase the pool.

## Final retained pool: intersection with C6.7's independent audit

C6.7's independent blinded Pass A audit (a structurally different method) had already reduced the 74 to 53 retained. Combining both: **36 records survive both the independent human-equivalent audit and the deterministic basis repair** — this is the final, doubly-verified exact-link pool. Full detail in `RC030_C68_AFFECTED_14_REPORT.md` and `generated/rc030_c68/final_exact_link_intersection.json`.
