# RC-030 Full Autonomous AI Audit — Baseline

Recorded 2026-07-16 before Phase 1+.

- HEAD: `394818675b0ed199e03cae1d89e38a488f5102ce`
- git status: nothing staged (untracked Part III artifacts from prior turns present, unchanged).
- Source DB hashes: `assembled_regimens.sqlite` = `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9`; `normalized_regimens.sqlite` = `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237`.
- Review DB hash: `review_workbench_p56.sqlite` = `3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29`; `review_decisions` = 0; all 9,153 tasks `PENDING`.
- Active calculation-eligible count: **0 / 2,675**.
- Approved-object count: **0**.
- Owner-event count: 1 real owner event exists (regimen 6657, `REMAINS_AMBIGUOUS`) in the owner's browser localStorage; not reachable/modifiable from this turn's files.
- AI pre-review event count (prior turn): 60 (`RC030_AI_PRE_REVIEW_EVENTS.json`).
- PDF coverage: 193/193 (100%) available across approved storage (`RC030_PDF_COVERAGE_GAP_REPORT.md`).
- Parser version (`semantics_parser.py` sha256, first 16): `78932988d6167074`.
- Interface version: `owner-review-interface-v2` / `owner-control-sample-v1`.
- Validation schema version: `OWNER_FIDELITY_SCHEMA_VERSION = 1`.

## Required baseline check
- calculation eligible = 0 ✅
- approved objects = 0 ✅
- owner verdict count unchanged (1, untouched) ✅
- Clinical Engine disconnected ✅
