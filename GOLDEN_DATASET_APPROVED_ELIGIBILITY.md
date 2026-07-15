# Golden Dataset Approved-Data Eligibility — Phase 11

Generated: 2026-07-15.

## Rule applied

Per Phase 11 of the physician-review-pilot mandate: the Golden Dataset is **not** run against draft data. A case may only be run once an eligible, `PHYSICIAN_APPROVED` `ClinicalRegimen` backs it.

## Current approved-object count

**0** (verified in [PHYSICIAN_PILOT_ACTIVATION_BASELINE.md](PHYSICIAN_PILOT_ACTIVATION_BASELINE.md) — database-wide, across all 9,153 review tasks, not just the 30-task pilot). No `ClinicalRegimen` in the system currently qualifies as approved data by any legitimate governed decision, because no human review decision of any kind has yet been recorded.

## Classification of all 7 Golden Dataset cases

| Case | Classification | Reason |
|---|---|---|
| `cap_penicillin_allergy.json` | `APPROVED_DATA_NOT_AVAILABLE` | No approved `ClinicalRegimen` exists anywhere in the system |
| `diagnosis_acute_sinusitis_gaimorit.json` | `APPROVED_DATA_NOT_AVAILABLE` | Same |
| `diagnosis_cap_pneumonia.json` | `APPROVED_DATA_NOT_AVAILABLE` | Same |
| `diagnosis_cystitis_uncomplicated.json` | `APPROVED_DATA_NOT_AVAILABLE` | Same |
| `diagnosis_negative_gaimorit_not_chronic.json` | `APPROVED_DATA_NOT_AVAILABLE` | Same |
| `diagnosis_negative_tonsillitis_not_combined.json` | `APPROVED_DATA_NOT_AVAILABLE` | Same |
| `diagnosis_negative_tonsillitis_not_pharyngitis.json` | `APPROVED_DATA_NOT_AVAILABLE` | Same |

All 7 cases are `APPROVED_DATA_NOT_AVAILABLE` for the same reason: the approved-object count is 0 system-wide, so no case can yet draw on governed clinical data. None are run. No expected answer was changed to force a pass — none were attempted.

## Re-evaluation trigger

This document must be regenerated once any `ClinicalRegimen` reaches a legitimate `PHYSICIAN_APPROVED` state through the real Reviewer A → Reviewer B → (adjudication if needed) → Medical QA Lead sign-off pipeline. At that point, each case should be re-classified individually based on whether its specific target diagnosis/regimen now has approved backing.
