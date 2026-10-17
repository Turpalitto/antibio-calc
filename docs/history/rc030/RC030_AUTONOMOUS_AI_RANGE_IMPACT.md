# RC-030 Autonomous AI Audit — Range Impact

Every AI verdict of CORRECT_RANGE_* checked against the stored scalar dose.

| regimen | source range | stored dose | stored == lower? | classification |
|---|---|---|---|---|
| 6121 | 20.0–40.0 | 20.0 | True | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |
| 6092 | 40.0–50.0 | 40.0 | True | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |
| 6579 | 45.0–60.0 | 45.0 | True | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |
| 7644 | 75.0–80.0 | 75.0 | True | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |
| 6580 | 45.0–60.0 | 45.0 | True | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |
| 5534 | 15.0–20.0 | 15.0 | True | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |
| 6073 | 80.0–90.0 | 80.0 | True | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |
| 6074 | 500.0–1000.0 | 500.0 | True | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |
| 6075 | 500.0–1000.0 | 45.0 | False | RANGE_SEMANTICS_CORRECT_VALUE_INCOMPLETE |

All range rows: parser day/dose direction is correct, but the stored scalar keeps only the lower bound (confirmed = lower in every case). **All remain calculation BLOCKED** — no range row could be safely calculated without a source-backed `dose_max`. Root cause: `medical_normalizer/drug_parser.py:139` (RC030_RANGE_LOSS_STAGE_RCA.md).
