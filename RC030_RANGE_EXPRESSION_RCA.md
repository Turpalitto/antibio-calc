# RC-030 Range Expression RCA — Why `RANGE_PER_DAY`/`RANGE_PER_DOSE` = 0

## Method

Independently searched three layers for numeric dose-range expressions (`N–M мг`, `N-M мг/кг`, "от N до M", etc.):
1. `assembled_regimens.source_quote` (verbatim source text, 2,675 rows)
2. `assembled_regimens.dose`/`unit` (the numeric fields the RC-030 parser actually consumes)
3. The RC-030 parser's own code path (`dose_verification_sandbox/parser.py`, `semantics_parser.py`)

## Finding — root cause located precisely, in code

`dose_verification_sandbox/semantics_parser.py:262`:
```python
is_range = expr.numeric_min != expr.numeric_max
```
`expr` comes from `parse_dose_expression(dose, unit, frequency)` (`parser.py`), which is called with a **single scalar** `dose` value — the regimen's `dose` column. Inside `parse_dose_expression` (`parser.py:97-98`):
```python
numeric_min = dose
numeric_max = dose
```
**`numeric_min` and `numeric_max` are set to the same value by construction, every time, because the function is only ever given one number.** `is_range` can therefore never evaluate `True` — not because the parser fails to recognize a range in text, but because **the range was already collapsed to a single scalar before the parser ever saw it.**

## Where the range is actually lost

Searched `assembled_regimens.source_quote` for `N–M мг`/`N-M мг/кг`-style patterns near the recorded dose: **348 of 2,675 rows (13%)** contain a genuine textual range in `source_quote`, but `dose` always holds a single number. Three concrete, hash-verifiable examples (live-queried, not paraphrased):

| regimen_id | `dose` field | `source_quote` (verbatim) | What happened |
|---|---|---|---|
| 5660 | `20.0` | "новорожденным до 2 нед – **20–50** мг/кг/сут" | Lower bound kept, upper bound (50) discarded |
| 5671 | `500.0` | "внутрь **500 - 1000** мг 3 раза в сутки" | Lower bound kept, upper bound (1000) discarded |
| 5683 | `50.0` | "Цефтриаксон\*\*  50-80 мг/кг" | Lower bound kept, upper bound (80) discarded |

The pattern is consistent across all three examples: **the lower bound of the range is what survives into the numeric `dose` field; the upper bound is dropped.**

## Corroborating schema evidence

`normalized_regimens` (the layer upstream of `assembled_regimens`) has **`duration_min`/`duration_max`** as a proper range pair, but only a single **`dose`** column — no `dose_min`/`dose_max`. Whoever built the normalizer schema already solved this problem for duration but never extended the same pattern to dose. This is strong independent evidence that the collapse happens at or before normalization, not in the RC-030 sandbox (which was only ever built in 2026-07 and reads `dose` as delivered).

## Classification

**Cause C: range lost during normalization** (the `normalized_regimens`/`assembled_regimens` schema has no dose-range columns, only a scalar `dose`, while an equivalent-purpose `duration_min`/`duration_max` pair exists one column over) — **not** a parser gap (D was ruled out: the parser's `is_range` logic is structurally sound and would work correctly if ever given two different numbers; it just never receives them) and **not** "no ranges exist" (A was ruled out: 348 rows have a genuine range in verbatim source text).

## Consequence for RC-030

This is a second, independent instance of the same class of defect RC-030 itself was opened for (`ROOT_CAUSE_REGISTER.md`'s RC-030 entry: "assembled_regimens's unit column cannot distinguish per-single-administration from per-day dosing") — a real piece of clinical information present in the source PDF that the assembly schema has no column to hold, so it gets silently collapsed to the nearest thing the schema *can* represent. The RC-030 sandbox's read-only semantics reconstruction cannot recover this either, because it currently trusts the `dose` column rather than re-deriving `numeric_min`/`numeric_max` from `source_quote` text directly.

## Recommendation (not implemented — decision only)

A future, separately-scoped fix would extend the additive semantics layer to re-derive `numeric_min`/`numeric_max` from a regex over `source_quote` (mirroring the existing max-dose extraction pattern in `semantics_parser.py`) instead of trusting the pre-collapsed `dose` column, when a range pattern is present in the quote. This is a parser enhancement, not a schema change, and does not require touching `assembled_regimens.sqlite`. It is not implemented in this turn — flagged as a candidate follow-up, consistent with `RC030_DOSE_SEMANTICS_ARCHITECTURE_DECISION.md`'s recommendation to keep the sandbox additive until a semantic type actually clears validation.
