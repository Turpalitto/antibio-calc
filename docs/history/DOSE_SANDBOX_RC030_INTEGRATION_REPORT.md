# DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md

Status: RC-030 Phase 9 integration report.

## What changed in the sandbox

- New modules: `semantics_models.py`, `semantics_parser.py`, `semantics_store.py`,
  `semantics_integration.py`, `ambiguity_workflow.py`. None modify `parser.py`, `calculator.py`,
  `verify.py`, `models.py`, or `assembled_regimens.sqlite` — all additive.
- `calculator.apply_max_dose()` gained an optional `source_max_single_dose` parameter (previously
  only daily-dose capping existed); this is a backward-compatible signature change (new parameter
  defaults to `None`), verified by re-running all 45 pre-existing P5.6 tests unchanged.
- `semantics_integration.calculate_from_semantics()` is the new entry point: takes a `DoseSemantics`
  + patient weight, returns `(eligibility, reasons, DoseCalculationTrace)` — using the *same,
  unmodified* `calculate()` arithmetic as before, just no longer starved of `denominator_time`.

## Eligibility rule (Phase 9)

```
ELIGIBLE  — semantic_type in {WEIGHT_PER_DAY, WEIGHT_PER_DOSE, FIXED_PER_DAY, FIXED_PER_DOSE,
                               RANGE_PER_DAY, RANGE_PER_DOSE}
            AND numerator_unit is resolved
            AND regimen_version is not older than the latest known version for this regimen_id

BLOCKED   — semantic_type in {UNPARSED, AMBIGUOUS, MISSING, NOT_APPLICABLE}
            OR numerator_unit could not be resolved
            OR regimen_version is stale
```

Missing frequency is *not* an eligibility blocker by itself — `calculate()` already handles it by
computing whichever of {single, daily} dose it can and warning `FREQUENCY_NOT_AVAILABLE` for the
other, exactly as in the original P5.6 behavior.

## Idempotent rebuild (Phase 8)

`semantics_store.rebuild_store()` is content-hash-deduplicated on `(regimen_id, regimen_version,
content_hash)`. Verified: running it twice against the same 50 real regimens produced `{inserted: 50,
skipped_unchanged: 0}` then `{inserted: 0, skipped_unchanged: 50}` — no duplication, no data loss,
safe to re-run on every sandbox session. A genuine change (different parser version or different
source data) adds a new row rather than overwriting the old one, preserving history for audit.

## Worked example: the exact case that started RC-030

Regimen `5574` (**джозамицин**, diagnosis A63.8) — `dose=50, unit="mg/kg", frequency=2.0` — was the
canonical `BLOCKED/AMBIGUOUS_PERIOD` case cited in the original P5.6 report. *(Correction: an earlier
version of this document mislabeled this regimen's antibiotic as "Азитромицин" — a citation error on
my part, not a database defect. See `ROOT_CAUSE_REGISTER.md` — RC-031 retracted. The dose numbers
below were always computed from the real regimen 5574 data; only the drug name label was wrong.)*

```
source_quote fragment matched: "в сутки"
semantic_type: WEIGHT_PER_DAY
eligibility: ELIGIBLE
weight_kg: 18.0
daily dose: 50 × 18 = 900 mg/day
single dose: 900 ÷ 2 = 450 mg/dose
calculation_status: OK
```

This regimen is now fully calculable, with the exact source fragment that justified the
classification displayed alongside the number — satisfying Phase 9's requirement to show "original
source expression, resolved semantic type, evidence used, parser confidence, ambiguity reason,
calculation eligibility" together.

## Test coverage added

`tests/dose_verification_sandbox/test_semantics_parser.py` (18 tests) and
`test_ambiguity_workflow.py` (2 tests) — full suite is now 66/66 passing (was 45/45 before RC-030).
Covers: explicit per-day/per-dose Russian signals, spelled-out frequency counts, the frequency=1
algebraic shortcut, genuine no-signal ambiguity, max-dose extraction (including the "не более 24
часов" duration-vs-dose exclusion test), unsupported/compound units, stale-version blocking,
idempotent rebuild, no-mutation-of-input, no-`clinical_engine`-import, and that BLOCKED cases still
correctly report `NOT_AVAILABLE` (not `PASS`) for max_dose/rounding through the new semantics path.
