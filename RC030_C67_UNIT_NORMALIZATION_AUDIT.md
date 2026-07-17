# RC-030 / C6.7 Part VIII (Phase 11) — Unit-Normalization Audit

## Scope

Audits whether the C6.5 fix to `dose_verification_sandbox.span_attribution._base_unit()` (reusing `medical_normalizer.dictionary.UnitNormalizer` for Cyrillic↔Latin script canonicalization) creates false equivalence, per the required test matrix.

## Script-canonicalization equivalence tests (the actual C6.5 fix)

Verified directly against `_base_unit()`:

| Pair | Result | Correct? |
|---|---|---|
| `mg` vs `мг` | equal (`mg`) | ✅ correct — same unit, different script |
| `g` vs `г` | equal (`g`) | ✅ correct |
| `mcg` vs `мкг` | equal (`mcg`) | ✅ correct |
| `IU` vs `ЕД` | equal (`iu`) | ✅ correct |
| `mmol` vs `mg` | not equal | ✅ correct — genuinely different units, correctly rejected (mmol not in `UNIT_NORMALIZATION`, returned as-is, no false match) |
| `xyz` (unknown) vs `мг` | not equal | ✅ correct — unsupported unit stays blocked, not silently coerced |
| `''` (empty) vs `мг` | not equal | ✅ correct |
| `mg/kg` vs `мг / кг` (spacing variant) | equal (`mg`) | ✅ correct — same leading token regardless of the DB's internal spacing |

**The audited script-canonicalization fix itself is sound** — it only ever equates genuinely-equivalent Cyrillic/Latin unit tokens, and never coerces a genuinely different unit (mmol, unknown tokens) into a false match.

## Pre-existing defect found (not introduced by the audited commit, but newly surfaced by this audit)

`_base_unit()` compares only the **leading token before the first `/`**, discarding everything after it:

```
mg/kg        -> mg
мг/кг/сут    -> mg   (via мг -> mg)
mg           -> mg
```

Consequence: **absolute `mg`, per-kilogram `mg/kg`, and per-kilogram-per-day `mg/kg/day` all collapse to the same base unit `mg` and are treated as `unit_match = True` against each other.** This is a real dose-basis conflation, not merely a display/script issue — `mg` and `mg/kg` are not interchangeable quantities.

### Real occurrences in the 117-candidate pool

Checked every record's `structured_unit` (from `assembled_regimens`) against the regex-captured `range_unit_raw` (from the source quote) for a "has-`/`-shape" mismatch:

**14/117 records (12%) exhibit this pattern**, split into two severities:

**High severity — absolute vs. per-kilogram conflation (11 records):**

| regimen_id | classification | structured_unit | range as captured |
|---|---|---|---|
| 5917 | SAFE_EXACT_LINK | mg/kg | 20-40 **мг** |
| 5918 | SAFE_EXACT_LINK | mg/kg | 30-50 **мг** |
| 5441 | SAFE_EXACT_LINK | mg/kg | 20-40 **мг** |
| 5442 | SAFE_EXACT_LINK | mg/kg | 30-50 **мг** |
| 5475 | SAFE_EXACT_LINK | mg/kg | 25-50 **мг** |
| 5478 | SAFE_EXACT_LINK | mg/kg | 25-50 **мг** |
| 5514 | SAFE_SINGLE_CANDIDATE | mg/kg | 75-100 **мг** |
| 6638 | SAFE_SINGLE_CANDIDATE | mg/kg | 20-90 **мг** |
| 6072 | SAFE_SINGLE_CANDIDATE | mg (absolute) | 80-90 **мг/кг/сут** |
| 5526 | SAFE_SINGLE_CANDIDATE | mg (absolute) | 15-20 **мг/кг** |
| 5533 | SAFE_SINGLE_CANDIDATE | mg (absolute) | 15-20 **мг/кг** |

**Root cause, confirmed by direct quote inspection (5917/5918/5441 all cite the identical erythromycin sentence):**

> "Детям первых трех месяцев жизни - 20-40 мг на кг массы тела в сутки ..."
> ("For infants under 3 months — 20-40 mg per kg of body weight per day")

`find_range_spans()`'s regex (`_RANGE_RE`) only recognizes a fixed compact unit-token list (`мг/кг/сут|мг/кг|г/сут|г|мг|мл`, etc.) immediately following the number. When the source text spells the per-kg-per-day qualifier out in words ("мг **на кг массы тела в сутки**") rather than the compact form ("мг/кг/сут"), the regex captures only the bare "мг" and silently drops the qualifier — the *classification* and *lower/upper bound numbers* end up correct (20-40, 30-50 etc. are the right numbers), but the **recorded `unit_raw` field misrepresents the dose basis as absolute milligrams instead of mg/kg/day**. `_base_unit()`'s leading-token comparison then happens to let this through as `unit_match = True` only because the DB's own structured field independently says `mg/kg`, not because the engine verified the text's true basis.

**Risk:** if any downstream consumer ever trusted the manifest's `unit_raw`/`selected_range_span.unit_raw` field literally instead of cross-checking the DB's `structured_unit`, a per-kilogram pediatric dose could be misrepresented as an absolute dose — a severe, weight-dependent dosing error if calculation were ever activated (it is not; `calculation_eligibility = BLOCKED` for every one of these records regardless of this audit's outcome).

**Low severity — per-day annotation only, same substance basis, no `/kg` involved (3 records):**

| regimen_id | classification | structured_unit | range as captured |
|---|---|---|---|
| 6085 | SAFE_EXACT_LINK | g | 2.0-4.0 **г/сут** |
| 6110 | SAFE_SINGLE_CANDIDATE | g | 3.0-12.0 **г/сут** |
| 6111 | SAFE_SINGLE_CANDIDATE | g | 3.0-12.0 **г/сут** |

These are lower risk — both sides express the same absolute-gram substance quantity; the mismatch is only that the text explicitly marks "per day" (`/сут`) while the structured field doesn't carry that qualifier. Not a weight-basis conflation, but still an information-completeness gap worth flagging.

## Disposition impact

This finding **downgrades exact-link admission** for the 6 high-severity `SAFE_EXACT_LINK` records (5917, 5918, 5441, 5442, 5475, 5478) under the Phase 6 admission standard's "no unit basis mismatch" / "unit matches" requirement — the *engine's own unit-match signal is not trustworthy evidence of dose-basis correctness* for any record where the captured `range_unit_raw` lacks a `/kg` qualifier that the DB's `structured_unit` has (or vice versa). `6085` (low severity) is flagged but not necessarily disqualifying — see Part V disposition. See [RC030_C67_DOUBLE_PASS_REPORT.md](RC030_C67_DOUBLE_PASS_REPORT.md) and [RC030_C67_EXACT_LINK_DISPOSITION.md](RC030_C67_EXACT_LINK_DISPOSITION.md) for the applied dispositions.

## Recommendation (not applied in this pass — deterministic rule change requires its own commit + regression tests per the owner's Part VI constraints)

`_base_unit()` should compare the **full unit shape** (whether a `/kg` and/or `/day`-equivalent qualifier is present, not just the leading substance token) whenever the source text's captured unit and the DB's structured unit both carry (or could carry) a per-weight qualifier — including cases where the regex's fixed unit-token list needs to be extended to recognize the spelled-out Russian forms ("мг **на кг массы тела в сутки**", "мг **на 1 кг массы**", etc.) rather than silently truncating to the bare substance unit. This is a genuine deterministic-rule proposal, not a data relaxation — flagged for a future dedicated commit with its own adversarial regression tests, per the owner's explicit prohibition on relaxing rules to reduce workload without proof.

## Rejection-reason mapping (Phase 12)

Already verified sound in the commit-boundary audit (Part II): the diagnostic-only rejection-reason bug (`or`-chain always returning `"phase_conflict"`) was fixed in `6045eea` and is now a proper priority-ordered function (`_reject_reason`) that returns exactly one of `boundary value | "phase_conflict" | "unit_mismatch" | "no_valid_segment"` per rejected candidate — confirmed by direct code read, this list only covers *rejection* reasons for candidates that failed the `valid` filter inside `attribute()`, not the full Phase-12-required primary-reason taxonomy (`drug_missing`, `alternative_boundary`, `table_context`, `maximum_conflict`, `age_conflict`, `route_conflict`, `competing_range`, `not_true_range`, `source_corrupted`, `PDF_unavailable`) — the module's own classification constants (`ALL_CLASSIFICATIONS`) partially cover this (e.g. `DICTIONARY_GAP`, `AMBIGUOUS_TABLE_CONTEXT`, `WRONG_RANGE_ANCHOR`) but there is no single exhaustive mapping test asserting exactly-one-primary-reason-per-non-safe-result across the full taxonomy named in the owner's spec. **Flagged as a gap for Part XIII targeted tests, not fixed in this pass** (adding it is a test-suite change, not an engine behavior change, and is lower urgency than the unit-basis finding above).
