# FORMULATION_DATA_GAP_REPORT.md

Status: RC-030 Phase 7. QA / RESEARCH ONLY finding, read-only investigation.

## Question

Does exact, source-backed formulation concentration (mg/mL, tablet strength, etc.) exist anywhere
in the repository for the regimens the Dose Verification Sandbox works with (`assembled_regimens.sqlite`)?

## Finding

**No — not linked to `assembled_regimens.sqlite` regimens.** Concentration data exists in exactly one
place in the repository: `db/antibio_db.json` (the hand-curated, 28-drug dataset behind
`antibiotic_calc.html`), whose schema (`db/schema.json`) defines:

```
form.concentration_mg_per_ml            (oral suspension/solution)
dilution.concentration_standard_mg_ml   (injectable, standard dilution)
dilution.concentration_max_mg_ml        (injectable, maximum safe concentration)
```

This dataset is keyed by its own drug identity scheme, entirely independent of
`assembled_regimens.regimen_id`/`antibiotic` (free-text Russian drug names from guideline extraction).
There is no join key, mapping table, or shared identifier between the two datasets. `assembled_regimens.sqlite`
itself has **zero** concentration-related columns.

## Classification (per spec Phase 7 categories)

| Category | Applies? |
|---|---|
| A. source-backed formulation concentration exists (linked to the regimen in question) | **No** |
| B. only drug strength exists | **Partially** — `assembled_regimens.dose` is the strength/amount per the parsed unit, but that is not the same as a formulation's presentation concentration (mg per mL of a specific product) |
| C. product-specific data absent | **Yes**, for every `assembled_regimens` regimen |
| D. ambiguous | No — the absence is unambiguous, not a borderline case |
| E. external governed reference required | **Yes** — a real join (drug identity reconciliation between guideline free-text names and `db/antibio_db.json`'s curated drug list) would be required before any assembled_regimens row could safely use `db/antibio_db.json`'s concentration data, and that reconciliation does not exist and is out of scope for RC-030 |

## Consequence for the sandbox

`formulation_conversion` remains `NOT_AVAILABLE` for all 2,675 `assembled_regimens` rows, as already
implemented in `dose_verification_sandbox/verify.py`. `convert_to_volume()` remains implemented and
tested (see `test_calculator.py::test_exact_concentration_conversion`) for the day a real, linked
concentration source exists, but it is never invoked automatically against real data.

## What would close this gap

A drug-identity reconciliation project (out of scope here) mapping `assembled_regimens.antibiotic`
free-text names to `db/antibio_db.json`'s 28 curated drugs (or a larger successor dataset), with
explicit, reviewed confidence per mapping — not a fuzzy string match applied silently. Until that
exists, formulation conversion stays disabled for real data, by design.
