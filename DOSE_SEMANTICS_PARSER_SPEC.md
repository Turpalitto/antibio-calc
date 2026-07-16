# DOSE_SEMANTICS_PARSER_SPEC.md

Status: v1.0, IMPLEMENTED (`dose_verification_sandbox/semantics_parser.py`)

## Method

For each regimen row with a non-null `dose` and a parseable `unit` (reusing the existing P5.6
`parser.parse_dose_expression`), the classifier:

1. Locates the `dose` number as a literal token inside `source_quote` (trying integer, `g`-formatted,
   1/2-decimal, and comma-decimal variants — Russian source text uses `,` as the decimal separator).
2. Takes a bounded window of source text around that token (30 chars before, 90 chars after).
3. Searches the window for explicit Russian/English signals, in priority order:
   - **Per-dose signals** (dose is a single-administration amount): `"N раз(а) в сутки/день"`
     (digits or spelled-out — два/две/три/четыре/пять/дважды/трижды), `"каждые N часов"`,
     `"на введение"`, `"разовая доза"`, `"per dose"`/`"per administration"`.
   - **Per-day signals** (dose is the daily total): `"/сут"`/`"/сутки"`, bare `"в сутки"`,
     `"суточная доза"`, `"/day"`/`"per day"`.
4. If both signal types are found, picks whichever is textually **nearest** the dose token (not
   simply the first match) — see "Known limitation" below.
5. If neither is found, and `frequency == 1.0` exactly, resolves via the **algebraic shortcut**:
   with one administration per day, "per dose" and "per day" are the same number, so the ambiguity
   doesn't matter mathematically. This is arithmetic, not a clinical inference.
6. Otherwise: `AMBIGUOUS`.

Separately, a proximity-scoped `"не более N мг/г"` regex (mass units only, so duration phrases like
`"не более 24 часов"` are never mistaken for a dose) extracts a source-backed maximum, attached to
`max_daily_dose` or `max_single_dose` depending on this row's own resolved `time_denominator`.

## Explicit signal examples (real, from `assembled_regimens.sqlite`)

| Source fragment | Signal type | Resolved as |
|---|---|---|
| "10 мг на кг массы тела **в сутки**" | per-day | `WEIGHT_PER_DAY` |
| "3,0 г **каждые 8 часов**" | per-dose | `FIXED_PER_DOSE` |
| "1000мг **2 раза в сутки**" | per-dose | `FIXED_PER_DOSE` |
| "400–500 мг **два раза в день**" | per-dose (spelled-out) | `FIXED_PER_DOSE` |
| "25-50 мг/кг **каждые 12 ч**" | per-dose | `WEIGHT_PER_DOSE` |
| "0,5-1,0 мг/кг/**сутки**" | per-day | `WEIGHT_PER_DAY` |
| "6 мг/кг **1 раз в сутки**" | per-dose (also freq=1, moot) | `WEIGHT_PER_DOSE` |
| "50 мг/кг (детская дозировка), **но не более 2 гр.**" | max-dose | `max_daily_dose=2000` |

## Known limitation: combination-drug alternative attribution

When a single `source_quote` describes two alternative dosing regimens for a combination drug in one
sentence (e.g. *"по 500 мг + 125 мг 3 раза в сутки **или** по 875 мг + 125 мг 2 раза в сутки"*), the
frequency clause for the *second* alternative follows *two* numeric components, not one. The
nearest-match heuristic can attribute the *first* alternative's frequency phrase to the *second*
dose's row if the textual distance happens to be shorter (a short "или по" transition vs. a longer
"мг + 125 мг" separator). In the one concrete case found during Phase 1 validation (regimen 7620,
dose=875), this produced a **cosmetically wrong** `matched_fragment` display string ("3 раза в
сутки" instead of "2 раза в сутки") — but the resulting `semantic_type` (`FIXED_PER_DOSE`) was
still correct, because both alternatives in that sentence share the same per-dose semantics, and the
row's own `frequency` column (already correctly extracted upstream) is what the calculation actually
uses, not the displayed fragment. This is a **display/evidence-quality** limitation, not a
calculation-correctness bug. Not fixed in this pass (diminishing-returns NLP segmentation problem);
documented here per the spec's instruction to be honest about residual limitations rather than
over-engineer a fix.

## Explicitly NOT done

- No inference of per-dose-vs-per-day from frequency alone (except the algebraic freq=1 shortcut,
  which is not an inference).
- No table-header inheritance (`TABLE_HEADER_INHERITANCE`) — `assembled_regimens.sqlite` carries no
  table row/column structure to inherit from; this pathway is unreachable against this data source
  (0 cases, by construction, not by measurement).
- No max-dose value inferred from "typical adult dose" — only extracted when the source text itself
  states a numeric ceiling with an explicit "не более"/"максимальная" phrase.
