# DOSE_CALCULATION_TRACE_SPEC.md

Status: v1.0, IMPLEMENTED (`dose_verification_sandbox/calculator.py`, `models.DoseCalculationTrace`)

## Purpose

Defines the exact, deterministic sequence of steps the sandbox records for every dose calculation,
so the owner can audit each intermediate value rather than trusting a final number.

## Trace fields

| field | meaning |
|---|---|
| `calculation_status` | `OK` or `BLOCKED` |
| `steps` | ordered list of `TraceStep(label, formula, operands, result, unit)` |
| `warnings` | list of machine-readable reason codes (`AMBIGUOUS_PERIOD`, `DOSE_UNPARSED`, `FREQUENCY_NOT_AVAILABLE`, `MAX_DOSE_NOT_AVAILABLE`) |
| `final_min_single_dose` / `final_max_single_dose` | per-administration dose, range preserved |
| `final_min_daily_dose` / `final_max_daily_dose` | per-day dose, range preserved |
| `final_frequency` | administrations/day used |
| `final_unit` | mg / IU / mL |
| `rounding_status` | always `NOT_APPLIED` today — see `DOSE_ROUNDING_POLICY.md` |
| `exact_result_preserved` | always `True` |
| `max_dose_reason` | `SOURCE_MAX_DAILY_DOSE` or `MAX_DOSE_NOT_AVAILABLE` |

## Blocking conditions (calculation_status = BLOCKED)

1. `parser_status == UNPARSED` — dose/unit could not be structurally interpreted (missing dose,
   missing/empty unit, compound unit string, non-mass/volume/IU unit like `%` or `капли`).
2. `denominator_time is None` — the unit does not specify whether the dose quantity is per
   administration or per day (e.g. bare `"mg/kg"`). **This is the dominant blocking reason on real
   data today** — see Phase 15 pilot report.

When blocked, no `final_*` dose field is populated; only the reason is recorded. The sandbox never
assumes "per day" as a default, and never assumes "per dose" as a default.

## Worked example — mg/kg/day (from the spec's own illustration)

```
source: 50 mg/kg/day  (denominator_time = "day", explicit)
weight: 18 kg
daily calculation: 50 × 18 = 900 mg/day
frequency: 3/day
single dose: 900 ÷ 3 = 300 mg
maximum daily dose: MAX_DOSE_NOT_AVAILABLE (no source column carries one)
final: 300 mg per administration, 3×/day, 900 mg/day, rounding NOT_APPLIED
```

This exact case is `GC-002` in `data/golden_calculation_dataset.json` (Phase 16) and
`test_mg_per_kg_per_day` in `tests/dose_verification_sandbox/test_calculator.py`.

## Worked example — the case that actually blocks on real data

```
source: 10 mg/kg  (denominator_time = None — "mg/kg" alone does not say per-dose or per-day)
weight: 18 kg
calculation_status: BLOCKED
warning: AMBIGUOUS_PERIOD — refusing to guess
```

*(Correction: this section previously cited `regimen_id=5574` for this example — verified incorrect;
regimen 5574 actually has `dose=50, antibiotic=джозамицин`, not `dose=10, antibiotic=Азитромицин`. The
regimen this example was actually describing was most likely `regimen_id=6138` (Азитромицин,
`dose=10, unit=mg/kg`, diagnosis A02.0–A02.9, source_quote containing "10 мг/кг веса в сутки") based
on matching the diagnosis code recorded at the time, though the original browser session did not log
the regimen_id explicitly enough to confirm with certainty. Note that regimen 6138, under the current
(post-RC-030) classifier, now resolves to `WEIGHT_PER_DAY`/`UNAMBIGUOUS` rather than `BLOCKED` — this
example describes the pre-RC-030 P5.6 sandbox's behavior, not current behavior. See
`ROOT_CAUSE_REGISTER.md` — RC-031 retracted — for the full correction.)*

## Range handling

When `numeric_min != numeric_max` (never occurs in real `assembled_regimens` data — no range columns
exist — only reachable via synthetic fixtures, e.g. `GC-003`), both bounds are carried through every
step independently. No midpoint, minimum, or maximum is silently chosen.

## Maximum dose

`apply_max_dose(trace, source_max_daily_dose)` is a separate, explicit call — never invoked
automatically by `calculate()`. Because `assembled_regimens.sqlite` has no max-dose columns, it is
never called against real data today; every real trace reports `max_dose_reason =
MAX_DOSE_NOT_AVAILABLE`.
