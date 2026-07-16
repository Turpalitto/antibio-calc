# DOSE_SEMANTICS_MODEL.md

Status: v1.0, IMPLEMENTED (`dose_verification_sandbox/semantics_models.py`,
`semantics_parser.py`, `semantics_store.py`). Additive to the P5.6 sandbox; does not modify
`assembled_regimens.sqlite`, `ClinicalRegimen`, or `TherapeuticOption`.

## Why this exists

RC-030 (see `ROOT_CAUSE_REGISTER.md`): `assembled_regimens.sqlite` stores a dose as a bare number +
unit string (`dose=50, unit="mg/kg"`) with no column stating whether that number is per single
administration or per day. The P5.6 sandbox correctly refused to guess and reported `BLOCKED` on
every real case. This model adds a separate, additive semantic layer, derived by reading
`source_quote` text near the dose value for explicit signals — never by inferring from common
medical practice.

## `DoseSemantics` (per regimen version, additive)

| field | meaning |
|---|---|
| `semantics_id` | opaque id, new on every computation |
| `regimen_id`, `regimen_version` | pins to a specific `assembled_regimens` row |
| `semantic_type` | one of 10 allowed values (below) |
| `numeric_min`/`numeric_max` | carried through from unit parsing (always equal — no ranges in source) |
| `numerator_unit` | mg / IU / mL |
| `weight_denominator` | bool — is the dose per-kg |
| `time_denominator` | `"day"` \| `"dose"` \| `None` |
| `administration_scope` | the matched source text fragment, or the algebraic-shortcut note |
| `frequency` | administrations/day, from the source column |
| `max_single_dose`/`max_daily_dose` | only set when a source-backed `не более N мг` phrase was found near this dose |
| `source_expression`/`normalized_expression` | raw dose+unit string |
| `parser_status` | `PARSED` \| `UNPARSED` |
| `ambiguity_status` | one of 5 values (below) |
| `provenance` | source PDF/page/guideline_id + any matched max-dose text |
| `derived_from` | `assembled_regimens.sqlite:<regimen_id>:<version>` |
| `confidence` | carried from the source row |
| `matched_fragment` | duplicate of `administration_scope`, kept for display convenience |

### Allowed `semantic_type` values

```
WEIGHT_PER_DAY   WEIGHT_PER_DOSE   FIXED_PER_DAY   FIXED_PER_DOSE
RANGE_PER_DAY    RANGE_PER_DOSE    UNPARSED        AMBIGUOUS
MISSING          NOT_APPLICABLE
```

`RANGE_PER_DAY`/`RANGE_PER_DOSE` are defined but unreachable against real `assembled_regimens` data
(no range columns exist in the schema) — only reachable via synthetic fixtures.

### Allowed `ambiguity_status` values

```
UNAMBIGUOUS                    — explicit textual signal found, unambiguous
RESOLVED_BY_FREQUENCY_ONE      — frequency == 1 makes per-dose/per-day algebraically identical
AMBIGUOUS_NO_SIGNAL            — no explicit signal found in the source window
AMBIGUOUS_CONFLICTING_SIGNAL   — genuinely conflicting signals equidistant from the dose token
NOT_APPLICABLE                 — row is MISSING/UNPARSED/NOT_APPLICABLE; signal detection doesn't apply
```

## Relationship to the existing `DoseExpression`/`DoseCalculationTrace` (P5.6)

`dose_verification_sandbox/semantics_integration.py::semantics_to_expression()` converts a resolved
`DoseSemantics` into the pre-existing `DoseExpression` (P5.6) by populating `denominator_time` with
the now-resolved `time_denominator`. The unchanged `calculator.calculate()` function then proceeds
normally — RC-030 does not duplicate or replace the arithmetic engine, it only unblocks the one field
(`denominator_time`) that used to always be `None`.

## Storage

`semantics_store.py` persists `DoseSemantics` in a separate, additive SQLite file
(`dose_verification_sandbox/data/dose_semantics_store.sqlite`, gitignored, regenerable), append-only
and idempotent — see `DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md` for the rebuild semantics.
`assembled_regimens.sqlite` is never opened for writing by any part of this layer.

## Ambiguity resolution workflow

`ambiguity_workflow.py` / `AmbiguityResolution` lets the owner record a **source-fidelity**
classification of a genuinely `AMBIGUOUS` row (e.g. "I read page 12 of the PDF myself and it
confirms per-day dosing") — never a clinical interpretation. See `DOSE_SEMANTICS_PARSER_SPEC.md`
Phase 11 for the allowed resolution types. No resolution changes `clinical_approval`, which remains
`NOT_APPROVED` throughout.
