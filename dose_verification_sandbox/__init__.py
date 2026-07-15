"""Dose Calculation Verification Sandbox.

QA / RESEARCH ONLY. Not clinically approved. Not production Clinical Decision Support.

Read-only against assembled_regimens.sqlite. Never writes to any source clinical
database, never mutates approval or review state. See DOSE_VERIFICATION_SANDBOX_SPEC.md.
"""

QA_BANNER = "QA / RESEARCH ONLY — NOT CLINICALLY APPROVED — DO NOT USE FOR PATIENT CARE"
