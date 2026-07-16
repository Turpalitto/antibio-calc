# RC030_FALSE_POSITIVE_AUDIT.md

Status: RC-030 Evidence Validation, Phase 3. Independent structural risk audit — does **not** use
`semantics_parser`'s own classification as ground truth. Implemented in
`dose_verification_sandbox/semantics_risk_audit.py`.

## Method

For every row that `semantics_parser.classify_regimen()` resolved to one of the four "safe" types
(`WEIGHT_PER_DAY`, `WEIGHT_PER_DOSE`, `FIXED_PER_DAY`, `FIXED_PER_DOSE`), an independent module
re-derives the text span strictly between the dose token and the matched semantic-signal fragment,
and checks that span for boundary-crossing hazards the classifier itself does not check for:

| Risk factor | Detection | Meaning |
|---|---|---|
| `CROSSES_ALTERNATIVE_BOUNDARY` | `"или"` (or) present in the gap | signal may belong to an alternative regimen, not this dose |
| `CROSSES_DRUG_NAME_BOUNDARY` | `"**"` present in the gap (source text consistently wraps drug names in this marker — confirmed on 2,067/2,675 rows) | signal may belong to a different drug mentioned in the same combined sentence |
| `CROSSES_SENTENCE_BOUNDARY` | `.`/`!`/`?` followed by whitespace/end, present in the gap | signal is in a different sentence |
| `COMPETING_DOSE_NUMBER_BETWEEN` | another `N мг/г/гр/мл/ед/IU`-shaped token present in the gap | a different dose number sits between this row's dose and its claimed signal |
| `MIXED_AGE_GROUP_LANGUAGE` | pediatric wording (`дет-`/`ребен-`/`ребён-`/`педиатр-`) in the gap for a row whose own `age_group` is `adult`, or adult wording (`взросл-`) in the gap for a `child` row | signal may belong to the other age group's dosing sentence |

**A real bug was found and fixed while building this audit**: the initial version measured the gap
starting from the *first digit* of the dose token rather than *after* it, causing the dose token's
own number+unit to be counted as a "competing dose" on nearly every row (952/1,645, 57.9% — clearly
wrong). Fixed by advancing the gap start past the matched numeral before comparing. Re-run after the
fix dropped the count to a plausible, spot-checked-correct 263/1,645.

## Result (full corpus, n=1,645 parser-resolved rows)

| semantic_type | total | high_risk | clean |
|---|---:|---:|---:|
| FIXED_PER_DOSE | 579 | 131 (22.6%) | 448 |
| WEIGHT_PER_DAY | 461 | 116 (25.2%) | 345 |
| FIXED_PER_DAY | 525 | 49 (9.3%) | 476 |
| WEIGHT_PER_DOSE | 80 | 11 (13.8%) | 69 |
| **Total** | **1,645** | **307 (18.7%)** | **1,338 (81.3%)** |

Risk factor breakdown (a row can have more than one): `COMPETING_DOSE_NUMBER_BETWEEN` 263,
`CROSSES_ALTERNATIVE_BOUNDARY` 46, `CROSSES_DRUG_NAME_BOUNDARY` 40, `MIXED_AGE_GROUP_LANGUAGE` 10,
`CROSSES_SENTENCE_BOUNDARY` 7.

## Spot-check of flagged cases (manual reading of 15 real flagged rows)

- Regimens 5654/5655/5670/5656: `COMPETING_DOSE_NUMBER_BETWEEN` on combination-drug doses written as
  `"500 мг + 125 мг"` — the flag is **correct**: the stored `dose` column holds only the first
  component, and the classifier's signal (frequency phrase) sits after both components, so the "gap"
  legitimately contains a second, different drug-component number. Correctly high-risk.
- Regimens 5660/5661/5677/5678/5696: gap text like `"–50 мг/кг"`, `"-80 мг/кг"` — these are the
  **second half of a dash-separated range** (e.g. source text `"30-50 мг/кг"`) that
  `assembled_regimens.dose` collapsed to a single number (50). This reveals a **related, distinct
  finding**: some `assembled_regimens` rows may represent one end of a source-documented range that
  was flattened upstream (in the P5.3 assembly engine) to a point value — a data-fidelity question
  separate from RC-030's per-dose/per-day question, worth its own root-cause entry, not fixed here.
- Regimen 5680: gap `" или Ванкомицин в дозе "` — genuinely crosses into a different drug
  (Ванкомицин/Vancomycin) via "или". Correctly high-risk.
- Regimen 5689: multiple risk factors simultaneously (alternative + sentence + competing dose) on a
  penicillin/erythromycin alternative-regimen sentence. Correctly high-risk.
- Regimen 5657: `"...в дозах, не превышающих 2400/600 мг"` — crosses into a *maximum-dose* statement
  for a different alternative. Correctly high-risk (and a reminder that R6's max-dose extraction has
  the same boundary-crossing exposure — addressed in Phase 8).

All 15 manually re-read flags were judged **correctly flagged** (i.e., zero false triggers of the
risk audit itself in this spot-check) — the risk audit itself was not spot-checked to be
under-triggering (over-cautious in a way that hides real risk) beyond this sample; Phase 4 provides
the broader independent read.

## Consequence

The 1,338 "clean" rows (81.3% of parser-resolved, 49.9% of the full 2,675-row corpus) are the
candidate pool for possible `QA_ELIGIBLE` promotion in Phase 9's status model — **conditioned on**
Phase 4/5's stratified human validation actually confirming acceptable precision on a sample of them,
not on this automated check alone. The 307 high-risk rows are demoted and must not be treated as
resolved; they carry the same practical outcome as `AMBIGUOUS` until a human resolves them via the
Phase 11 ambiguity workflow.
