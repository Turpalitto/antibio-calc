# RC024_CLASS_LEVEL_ANALYSIS.md
## Class-Level REJECT Analysis · P5.5 · 2026-07-15
## Status: AUDIT COMPLETE — computed over the full 1,132 REJECT population, manually spot-verified

> Re-classifies the 1,132 REJECT `ClinicalRegimen` candidates (`P5.4_IMPLEMENTATION_REPORT.md`) into
> the taxonomy the mandate requires: A (therapeutic class recommendation), B (alternative therapy
> statement), C (specific regimen missing extraction), D (invalid/noise). This is a DIFFERENT cut of
> the same 1,132 rows than `RC024_DOSE_AUDIT_REPORT.md`'s A-F taxonomy (which asked "why is dose/
> route missing"); this one asks "is this REJECT actually a mis-modeled regimen, or a genuine defect."

## Method (corrected after an internal bug — recorded honestly)
The classifier was run once, produced `D_invalid_noise=372 (32.9%)`, and was NOT published at that
figure — inspection showed the real noise check (degenerate/fragment quotes) only caught 23 rows;
the other 349 were falling through a catch-all default for a case the first version of the logic
never explicitly handled (dose present, route missing — the P5.4-identified 378-row subset). This
is exactly the P5.4 lesson repeating: **verify before publishing.** The classifier was corrected to
explicitly handle every combination of (dose present/absent, route present/absent), re-run, and
sanity-checked (0 anomalies: no REJECT has both dose AND route present — consistent with Gate 1's
exact failure definition). Final classification below is the corrected, verified result.

## Classification (final, verified)

| Category | Definition | Count | % of 1,132 |
|---|---|---:|---:|
| **A — Therapeutic class recommendation** | No dose present, no dose text recoverable, `drug_original` names a drug CLASS or ATC group (e.g. "макролиды", "цефалоспорины 4-го поколения", "бета-лактамные антибактериальные препараты: пенициллины") rather than a single agent | **627** | **55.4%** |
| **B — Alternative therapy statement** | No dose present, quote explicitly lists 2+ SPECIFIC single drugs as alternatives ("ампициллин, амоксициллин+клавулановая кислота или ампициллин+сульбактам") without giving a dose for any | **25** | **2.2%** |
| **C — Specific regimen missing extraction** | A single, specific drug IS identified, and either (a) dose is present but route is missing, or (b) dose text is literally present in the quote but wasn't parsed into the field | **457** | **40.4%** |
| **D — Invalid/noise** | Quote is a degenerate fragment (near-empty, or dominated by non-Cyrillic table-shorthand codes with <5 Cyrillic characters) | **23** | **2.0%** |

**Partition verified complete and non-overlapping:** 627+25+457+23 = 1,132. Sanity check: 0 rows
have both dose AND route present while still being REJECT (confirms Gate 1's failure condition is
exactly "dose or route missing," consistently).

## Manual verification (spot-checked samples, not assumed)
- **A samples confirmed accurate**: "пенициллины широкого спектра действия", "фторхинолоны",
  "карбапенемы" — genuine class/group statements. **One outlier noted honestly**: regimen 7474's
  `source_quote` is about urinalysis frequency, unrelated to its `drug_original` — a
  `normalized_regimens` source-data misalignment (quote/drug mismatch), not a class statement. Left
  in category A (conservatively, since it has no dose either way) but flagged as a distinct data-
  quality issue, not silently absorbed.
- **B samples confirmed accurate**: multi-drug alternative lists with no dose for any listed drug.
- **C samples mostly confirmed** (specific drug + dose present, route missing, or dose text visible
  in the full quote beyond the display truncation). **One outlier noted**: regimen 5981's
  `drug_original` ("фторметолон 0,1%+тобромицин 0,3%") does not match its own `source_quote` (which
  discusses "дексаметазон") — another source-data misalignment, distinct from a genuine extraction
  gap. Both outliers are `normalized_regimens` upstream data-quality findings (registered below, not
  fixed here — `normalized_regimens.sqlite` is frozen for this program).
- **D samples confirmed accurate and revealing**: all inspected D rows are **tuberculosis regimen
  shorthand codes** ("H R/Rb Z E [S]", "5-18 Lfx/Mfx/Sfx Cs/Trd...") — standard WHO/Russian TB
  multi-drug regimen abbreviations extracted as bare table fragments, not prose. This is a genuine,
  distinct extraction gap specific to TB combination-regimen tables — not a candidate for
  `TherapeuticOption` (it is not a coherent recommendation statement at all in its current form).

## New findings registered (not fixed — consistent with the project's Root Cause discipline)
- **RC-025**: a small number of `normalized_regimens` rows have `source_quote` misaligned with
  `drug_original` (2 confirmed in manual spot-check of ~35 samples; population-wide count not yet
  measured). Upstream extraction/attribution defect, out of P5.5 scope (`normalized_regimens.sqlite`
  is not modified in this program).
- **RC-026**: TB combination-regimen tables extract as bare abbreviation-code fragments (D category,
  23 confirmed rows, likely more across the full corpus beyond the REJECT set) rather than
  structured regimens. A distinct, TB-specific extraction gap.

## What this means for RC-024
**55.4% + 2.2% = 57.6% of all REJECTs (A+B, 652 rows) are not defective regimens at all — they are
a different KIND of clinical knowledge** (a class-level recommendation or an alternatives list),
which the `ClinicalRegimen` model (designed for one concrete, dosed regimen) structurally cannot and
should not represent. This is the basis for `THERAPEUTIC_OPTION_RULES.md` and the new
`TherapeuticOption` type (§below, `clinical_engine/regimen/therapeutic_option.py`).

**40.4% (C, 457 rows) remain genuine `ClinicalRegimen` candidates** with a real, fixable-in-principle
extraction gap (route missing, or dose text unparsed) — these stay in the `ClinicalRegimen` pipeline,
correctly REJECT until the gap is closed (re-extraction, out of P5.5 scope, or the P5.4 route-
recovery pass, already applied where safely possible).

**2.0% (D, 23 rows) are TB-specific extraction noise** — neither a valid `ClinicalRegimen` nor a
`TherapeuticOption` candidate; flagged for a future targeted TB-table extraction fix (RC-026).
