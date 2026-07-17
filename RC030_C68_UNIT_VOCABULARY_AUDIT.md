# RC-030 / C6.8 Phase 2 — Unit Vocabulary Audit

## Method

Queried real data directly: all 2675 `assembled_regimens.unit` values (structured field), all `unit_raw` values actually captured by the current range regex across the 117 C6.7 candidates, and a targeted regex sweep of all 365 range-candidate `source_quote` strings for unit forms the spec's model anticipates but the current engine doesn't yet parse.

## Structured `unit` field — all 13 distinct values observed (2675 rows)

| Value | Count | Notes |
|---|---|---|
| `''` (empty) | 755 | non-dose or unstructured records |
| `mg` | 748 | absolute mass |
| `mg/kg` | 658 | per-kilogram |
| `g` | 462 | absolute mass |
| `IU` | 27 | activity units, already Latin-normalized |
| `капля` / `капли` | 5 + 5 | drops — administration-form unit, not a mass/activity dose at all |
| `%` | 5 | concentration/percentage, not a mass dose |
| `см` | 3 | centimeters — clearly not a dose unit (likely a data-quality artifact, e.g. a wound-size or catheter-length field misclassified as dose) |
| `мкг/кг` | 3 | per-kilogram, **Cyrillic, not yet Latin-normalized** even in the structured field — unlike `mg/kg` |
| `г; мг/кг` | 2 | **compound, semicolon-separated multiple units in one field** — a genuinely new case the current flat-string model cannot represent at all |
| `г; мг/кг/сут; мг/кг/сут` | 1 | compound, three units in one field |
| `ЕД/г` | 1 | activity-per-mass, a concentration-like basis |

**Real, previously-unhandled findings:** (1) `мкг/кг` shows the structured field itself isn't always Latin-normalized upstream — the C6.7 fix's script-canonicalization needs to keep working on this side too. (2) The 3 compound semicolon-separated values (`г; мг/кг`, `г; мг/кг/сут; мг/кг/сут`) cannot be represented by a single `DoseUnitSignature` at all — these need either a documented "compound unit, first token only" convention or a `MALFORMED_UNIT`/`unknown_tokens` classification; not silently picking the first token.

## `unit_raw` values actually captured by the current range regex (117 candidates)

| Value | Count |
|---|---|
| `мг/кг` | 32 |
| `мг/кг/сут` | 26 |
| `г` | 24 |
| `мг` | 22 |
| `мг/кг/день` | 10 |
| `г/сут` | 3 |

All 117 fall inside the regex's fixed alternation (`мг/кг/сут\|мг/кг/сутки\|мг/кг/день\|мг/кг\|г/сут\|г\|мг\|мл`) — expected, since these are exactly the classified-safe pool the regex could recognize by construction.

## Extended vocabulary sweep across all 365 range-candidate source quotes

| Pattern | Occurrences |
|---|---|
| `мкг` (mcg) | 0/365 |
| `мкг/кг/мин` (mcg/kg/min, continuous rate) | 0/365 |
| `ЕД` (IU) | **8/365** |
| `МЕ` (IU alternate spelling) | 0/365 |
| `ммоль` (mmol) | 0/365 |
| `м2`/`м²` (BSA) | 0/365 |
| `%` | 0/365 |
| `капл` (drops) | 0/365 |
| `мг/сут` without `/кг` (absolute mg/day) | 0/365 |
| `мг/введение`/`мг/приём` (explicit per-dose wording) | 0/365 |

**Real conclusion:** within this specific 365-record range-candidate corpus, the only genuinely observed unit form outside the current regex's coverage is **`ЕД` (IU), 8 occurrences**. `мкг` (mcg), `ммоль` (mmol), `м²` (BSA), `%`, drops, and explicit per-dose wording do not occur in this corpus at all. The spec's full `DoseUnitSignature` taxonomy (mcg/kg/min, mmol, m2, concentration denominators, etc.) is implemented as a general, governed model per Phase 1's explicit requirement — but per Phase 2's "do not add a synonym without a real observed or governed source," components with zero observed occurrences here are scaffolded from the **already-governed** `medical_normalizer.dictionary.UNIT_NORMALIZATION` dictionary (which already has `IU`/`thousand_IU`/`mcg` entries) rather than invented, and are marked as unobserved-in-this-corpus in the model's own test coverage.

## Recommendation for Phase 3 canonicalization scope

Given the real data: the highest-value, evidence-backed addition to the range regex/vocabulary is **IU/ЕД range recognition** (8 real occurrences currently unparseable as ranges at all — these are presumably landing in `NOT_A_DOSE_RANGE`, `DICTIONARY_GAP`, or similar buckets today, not silently misclassified as unit-compatible). The compound semicolon-separated structured-unit case (3 rows) is rare but must not silently pick the first token — `DoseUnitSignature.parse_status = MALFORMED_UNIT` with the raw value preserved in `unknown_tokens` is the fail-closed choice.
