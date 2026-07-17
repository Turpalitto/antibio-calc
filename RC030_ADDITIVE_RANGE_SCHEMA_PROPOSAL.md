# RC-030 Additive Range Schema — Proposal (not activated)

Design only. No database is migrated or mutated by this document.

## Proposed additive fields

| Field | Type | Populated by |
|---|---|---|
| `dose_min` | float, nullable | re-derived from `source_quote` by a new sandbox regex (mirrors `extract_max_dose_signal`'s pattern) |
| `dose_max` | float, nullable | same |
| `dose_is_range` | bool | `dose_min != dose_max` |
| `dose_range_raw` | str, nullable | the matched substring, e.g. `"20-50 мг/кг/сут"` |
| `dose_unit` | str | reuses existing `unit` column, unchanged |
| `dose_basis` | enum `{NORMALIZER_SCALAR, SANDBOX_RANGE_RECOVERY}` | provenance of `dose_min`/`dose_max` — did they come from the (lossy) `dose` column or from the sandbox's own re-derivation |
| `range_source_quote` | str | copy of `source_quote` at recovery time, for drift detection |
| `range_source_offsets` | `[start, end]` | character offsets of the matched range within `source_quote` |
| `range_provenance` | str | fixed value `"dose_verification_sandbox additive re-derivation, not normalizer-sourced"` |
| `range_confidence` | float | heuristic: 1.0 if the regex match's unit matches the row's `unit` column, lower otherwise |
| `source_regimen_version` | int | copy of `assembled_regimens.version` at recovery time, for staleness detection |

## Backward compatibility

**Fully additive.** No existing column changes type or meaning. `dose` (scalar) continues to mean exactly what it means today — the normalizer's already-collapsed value, with all the same downstream consumers (Clinical Engine, Review Workbench) unaffected. `dose_min`/`dose_max` would live only in a new sandbox-owned table or dict, not in `assembled_regimens.sqlite` itself (avoids touching the source database, per this program's standing constraint).

## Deterministic population rules

- **Scalar dose (no range detected in `source_quote`)**: `dose_min = dose_max = dose` (the existing normalizer value). No re-derivation needed, no new regex risk.
- **Explicit numeric range detected** (`N-M unit` pattern near the dose anchor): `dose_min`, `dose_max` set from the regex match; `dose_basis = SANDBOX_RANGE_RECOVERY`.
- **Alternatives are not ranges**: a `source_quote` containing "или" between two *different* dosing options (e.g. "500 мг 3 раза в сутки или 875 мг 2 раза в сутки") must not be misparsed as a range — the regex must anchor on a single hyphen/en-dash between two numbers with no "или"/comma/сентence break between them, and must reject a match that spans an "или".
- **Maximum-dose clauses are not ranges**: "не более 4 г/сут" or similar max-dose phrasing must not be captured by the range regex — reuse the existing `extract_max_dose_signal` exclusion patterns to keep the two regexes from double-matching the same text.
- **Loading/maintenance values are not ranges**: "нагрузочная доза X, поддерживающая доза Y" is two distinct doses for two distinct clinical moments, not a range of one dose — must be excluded by requiring the two numbers be immediately adjacent (single hyphen/en-dash, no intervening words).
- **Uncertain parsing**: if the regex can't confidently anchor a range without ambiguity, `dose_min`/`dose_max` remain `null` and the record's existing `calculation_eligibility` (already `BLOCKED`) is untouched — this proposal changes what evidence is *available for future human review*, not what's eligible for calculation today.

## Not implemented in this turn

This is a design proposal only, consistent with `RC030_DOSE_SEMANTICS_ARCHITECTURE_DECISION.md`'s recommendation to keep RC-030 additive and unvalidated until a semantic type actually clears the precision threshold. Building this out is real, separately-scoped follow-up work.
