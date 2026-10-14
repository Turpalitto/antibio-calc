# Golden Dataset Failure Analysis

Date: 2026-07-15  
Database: `C:\clinrec_downloader\normalized_regimens.sqlite`  
Command result: total 7; PASS 0; FAIL 7; ERROR 0.

Clinical Engine logic was not changed. Expected medical answers were not changed.

## Root causes

| Case | Observed | Single root-cause category | Evidence |
|---|---|---|---|
| `cap_penicillin_allergy` | two cefuroxime candidates accepted; no amoxicillin loaded/excluded | fixture invalid | Fixture author is `AI for demo`; it expects `amoxicillin`, but real DB has no normalized amoxicillin row. Relevant amoxicillin/clavulanate rows are REJECT and excluded by strict provider before safety stage. Fixture describes synthetic/RFC data, not real approved corpus state. |
| `diagnosis_acute_sinusitis_gaimorit` | actual guideline IDs `1220`, `1632`; expected `g_sinusitis` | fixture invalid | Provenance itself names real IDs 1220/1632, while expectation uses synthetic placeholder. |
| `diagnosis_cap_pneumonia` | actual ID `1963`; expected `g_cap_adult` | fixture invalid | Real index uses numeric IDs. Fixture provenance names 1770 but expectation remains synthetic and does not match current provider output. |
| `diagnosis_cystitis_uncomplicated` | actual IDs `1127`, `1643`; expected `g_cystitis` | fixture invalid | Provenance names real ID 1127; expectation uses synthetic placeholder. |
| `diagnosis_negative_gaimorit_not_chronic` | actual IDs `1220`, `1632`; expected `g_sinusitis` | fixture invalid | Positive assertion uses synthetic ID. Negative assertion therefore cannot certify intended acute/chronic distinction. |
| `diagnosis_negative_tonsillitis_not_combined` | actual ID `1269`; expected `g_cap_adult` | fixture invalid | CAP placeholder is unrelated to stated tonsillitis intent; no source page or physician verification supports expected ID. |
| `diagnosis_negative_tonsillitis_not_pharyngitis` | actual ID `1269`; expected `g_cap_adult` | fixture invalid | Same synthetic/unrelated expectation; provenance is only RFC text, not source guideline evidence. |

## Trace findings

Golden path was reproduced through query → diagnosis mapping → regimen provider → filtering → unmodified Engine → public output.

For allergy case, DiagnosisMatch selected 1198/1324/1770/1963. Strict regimen loading retained only two PASS cefuroxime rows from guideline 1963. Amoxicillin was never supplied to HardSafetyFilter, so expected amoxicillin exclusion cannot be asserted against this database.

## Gate decision

- Every current failure has a proven fixture-invalid root cause.
- This does not prove Engine clinically correct.
- Cases must not be edited to green without source guideline, page, medical justification and physician review state.
- Existing 7 files remain failing initial gate and must be replaced or governed through Golden review, not silently updated.
