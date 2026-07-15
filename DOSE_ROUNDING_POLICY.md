# DOSE_ROUNDING_POLICY.md

Status: ADOPTED (v1, sandbox-scoped)
Owner: Dose Calculation Verification Sandbox (P5.6)
Applies to: `dose_verification_sandbox/` only. Does not govern `antibiotic_calc.html`'s
UI display rounding, which predates this policy and is out of scope for this document.

## Policy

The sandbox's default and currently only supported rounding mode is:

```
NO_ROUNDING
```

- The exact mathematically computed result is always shown, in full floating-point precision.
- `DoseCalculationTrace.rounding_status = "NOT_APPLIED"` on every trace.
- `DoseCalculationTrace.exact_result_preserved = True` always — the exact value is never dropped from the trace even if a rounded value is shown alongside it in a future revision.
- No clinically-reviewed rounding rule (e.g. "round to nearest 25 mg", "round to nearest measurable syringe increment", "round to nearest half tablet") exists in this repository as an adopted, source-backed policy. Inventing one here would violate the sandbox's core constraint ("do not invent clinical rounding rules").

## Why no rounding mode exists yet

Rounding rules are clinical judgment calls (e.g., which increment is "practically administrable" for a given formulation) that require a physician or pharmacist to adopt, not something to be inferred from arithmetic. Per `DOSE_VERIFICATION_SANDBOX_SPEC.md` Phase 8, only source-backed rounding modes may be added:

- nearest measurable volume
- nearest tablet fraction
- source-defined increment

Each of these requires provenance (a cited source stating the increment) before it can be added as a governed mode.

## How to add a governed rounding mode later

1. Obtain a source-backed rounding rule (guideline text, formulation packaging data, or physician sign-off) with provenance (document + page/quote).
2. Add the rule as a new named mode in this document with its provenance citation.
3. Extend `dose_verification_sandbox/calculator.py` to support the new mode explicitly, gated by the presence of source data — never as a silent default.
4. Update `test_source_backed_rounding_not_yet_governed` in `tests/dose_verification_sandbox/test_calculator.py` (or add a new test) exercising the new mode's arithmetic.

Until such a mode exists, `rounding_status` remains `NOT_APPLIED` for every regimen in `assembled_regimens.sqlite`, and the sandbox's Phase 10 `rounding` verdict reports `NOT_AVAILABLE`, never `PASS`.
