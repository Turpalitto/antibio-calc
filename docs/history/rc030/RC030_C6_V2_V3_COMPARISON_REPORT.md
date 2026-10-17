# RC-030 C6 — V2 (naive) vs V3 (span-linked) Comparison

Full data in `RC030_C6_V2_V3_COMPARISON.json` (compact, aggregate-only — no per-record clinical excerpts).

## Summary

| Metric | Value |
|---|---|
| V2 original range candidates | 365 |
| V2 trustworthy (scalar == recovered lower bound) | 186 |
| V2 suspect (scalar != recovered lower bound) | 179 |
| V3 input (all 179 real suspect records, re-processed) | 179 |
| V3 `SAFE_EXACT_LINK` | 0 |
| V3 `SAFE_TABLE_LINK` | 0 |
| V3 `SAFE_SINGLE_CANDIDATE` | 0 |
| V3 safe total | **0** |
| V3 ambiguous total | 46 (`AMBIGUOUS_ALTERNATIVE_BOUNDARY` 23, `AMBIGUOUS_TABLE_CONTEXT` 12, `AMBIGUOUS_MULTIPLE_DRUGS` 10, `AMBIGUOUS_LOADING_MAINTENANCE` 1) |
| V3 `WRONG_RANGE_ANCHOR` | 111 |
| V3 `NOT_A_DOSE_RANGE` | 22 |
| Rows where V2's naive first-range selection is confirmed unsafe by V3 | 179 / 179 |
| Unrelated clinical-field changes | **0** |
| Calculation eligible before/after | 0 / 0 |
| Approved objects before/after | 0 / 0 |
| Authoritative `assembled_regimens.sqlite` hash before/after | identical (`9f505d08...`) |

## Interpretation

V3 does not produce a single new migration candidate from the 179-record SUSPECT set. This is expected given how that set was constructed (Part I of a prior turn): it is precisely the subset where the naive heuristic's own first-range guess already disagreed with the structured scalar dose, i.e. the hardest, most adversarial cases (multi-phase surgical-timing dosing, multi-drug "Или"-separated alternatives, malformed multi-number OCR artifacts). Spot-checked examples (`RC030_C6_ARCHITECTURE_AUDIT.md`) confirm V3's rejections are *correct* rejections, not engine failures — in each sampled case, either the range genuinely belongs to a different drug/phase, or the source text does not contain enough structural information to link it safely without the (currently unavailable in this environment) table/PDF layer.

**Required checks — all satisfied:**
- Unrelated clinical-field changes: 0 (V3 never touches any field outside the experimental range columns, and those are not written to any authoritative table in this turn)
- Calculation eligibility: 0 before, 0 after
- Approvals: 0 before, 0 after
- Authoritative `assembled_regimens.sqlite` hash: unchanged
