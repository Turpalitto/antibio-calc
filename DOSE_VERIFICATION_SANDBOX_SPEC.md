# DOSE_VERIFICATION_SANDBOX_SPEC.md

Status: v1.0, IMPLEMENTED
Scope: `dose_verification_sandbox/` — QA / RESEARCH ONLY. Not physician approval. Not production
Clinical Decision Support. Does not start P6. See `DOSE_VERIFICATION_SANDBOX_AUDIT.md` (Phase 0)
for the pre-implementation audit this spec is built on.

## Purpose

A local, read-only tool for the project owner to select a diagnosis (MKB/ICD), an antibiotic, and
patient parameters, and inspect exactly how a source-derived dose regimen would be calculated —
with every arithmetic step visible, every ambiguity surfaced instead of guessed, and every result
labeled with its true approval state (currently: none approved).

## Architecture

```
assembled_regimens.sqlite (read-only, source of truth for regimen data)
        │  snapshot.py — opens mode=ro, never writes
        ▼
data/snapshot_latest.json (versioned, exported snapshot)
        │
        ├── Python path: parser.py → calculator.py → verify.py → issues.py / golden.py / pilot.py
        │     (used by tests/, pilot.py, golden.py)
        │
        └── Browser path: ui/dose_verification_sandbox.html
              loads snapshot_latest.json via a local <input type=file> (FileReader) —
              no fetch(), no CORS dependency, works fully offline from disk.
              Contains a hand-ported copy of parser.py/calculator.py's logic in JS
              (kept in sync manually; both are covered by the same conceptual test matrix).
```

No component in this tree imports `clinical_engine`, opens any source database for writing, or can
mutate `status`/`review_status`/`approved_by` on any regimen. See `test_invariants.py`.

## Data model

- **Input**: `DoseVerificationInput` (`models.py`) — validated; invalid input raises `UnsupportedInput`
  (`UNSUPPORTED_INPUT`), never silently coerced.
- **Dose expression**: `DoseExpression` — output of `parser.py`, structured interpretation of the
  regimen's `dose`/`unit`/`frequency` columns. `parser_status` is `PARSED` or `UNPARSED`.
- **Calculation trace**: `DoseCalculationTrace` — output of `calculator.py`. `calculation_status` is
  `OK` or `BLOCKED`. Every arithmetic step is recorded in `.steps`; every reason a value could not be
  computed is recorded in `.warnings`.
- **Verification result**: `DoseVerificationResult` — eight verdicts (`source_fidelity`, `parsing`,
  `arithmetic`, `unit_consistency`, `max_dose`, `rounding`, `formulation_conversion`,
  `clinical_approval`). `clinical_approval` is hard-locked to `NOT_APPROVED` by the dataclass itself.
- **Owner comparison**: `OwnerComparison` — owner-entered expected values, diffed against the trace,
  classified into one of nine QA categories (never a physician-approval category).
- **Issue**: `DoseCalculationIssue` — appended to `data/issues.json` via `issues.py`. Local file only.

## The one real finding this sandbox already produced

Every one of the 12 real regimens sampled in the Phase 15 pilot (`data/pilot_report.json`) resolved
to `calculation_status = BLOCKED`, primarily with `AMBIGUOUS_PERIOD`: `assembled_regimens.sqlite`'s
`unit` column (e.g. `"mg/kg"`) does not distinguish per-single-dose from per-day, and no other column
carries that distinction either. The sandbox refuses to guess it. This is recorded as 12 open
`DoseCalculationIssue` records and should be escalated to `ROOT_CAUSE_REGISTER.md` as a genuine data
model gap — not a sandbox defect.

## Non-goals

- Does not replace or call into `clinical_engine/stages/dose_calculation.py` or any other engine stage.
- Does not compute renal-adjusted doses (no numeric renal formula exists anywhere in the repo).
- Does not invent a rounding rule (see `DOSE_ROUNDING_POLICY.md`).
- Does not perform formulation/concentration conversion against real data (no such columns exist in
  `assembled_regimens.sqlite`); the arithmetic itself (`convert_to_volume`) is implemented and tested
  against synthetic input for when source-backed concentration data becomes available.

## Files

See "Exact files proposed for change" in `DOSE_VERIFICATION_SANDBOX_AUDIT.md` — implemented as specified.
