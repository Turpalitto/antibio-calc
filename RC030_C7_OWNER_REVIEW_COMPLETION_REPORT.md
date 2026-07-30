# RC-030 C7 Owner Review Completion Report

Date: 2026-07-30

> **Final reconciliation completed later the same day.** The intermediate
> 157-event state and required-next-step section below are retained as audit
> history. Current terminal state is 182 events, 113/113 regimens, zero
> validation issues, and zero substantive mismatches. See
> `RC030_C7_OWNER_VS_AI_COMPARISON_REPORT.md`.

## Completion observed in the live UI

All 11 owner-review batches reached their full counters:

| Batch | Mode | Complete |
|---|---|---:|
| 01 | exact link | 12/12 |
| 02 | exact link | 12/12 |
| 03 | exact link | 12/12 |
| 04 | engine disagreement | 11/11 |
| 05 | unit basis | 12/12 |
| 06 | unit basis | 12/12 |
| 07 | unit basis | 12/12 |
| 08 | unit basis | 7/7 |
| 09 | table context | 8/8 |
| 10 | single candidate | 12/12 |
| 11 | single candidate | 3/3 |
| **Total** |  | **113/113** |

The completed browser-local history was later recovered as 157 append-only
events covering 113/113 unique regimens. Schema, identity, and supersession
validation returned zero issues. One consolidated export and 11 per-batch
exports were saved under
`%USERPROFILE%\Downloads\RC030_C7_owner_exports_2026-07-30T05-33-36-881Z`.
UI completion and valid review evidence are not clinical approval.

## Owner-observed extraction defect

Record: `regimen_id=6068`

- PDF: `Острый ларингит.pdf`
- page: 16
- drug: amoxicillin
- flattened extraction: `5001- 10002 мг`
- visual PDF reading: `500¹–1000² мг`
- clinical numeric range after removing superscript footnote markers:
  `500–1000 мг`
- frequency: three times daily

The superscript `1` and `2` are footnote markers, not numeric digits in the
dose. This occurrence is unique in the 113-record C7 queue for the literal
`5001- 10002` corruption. It was also identified independently in
`RC030_C7_AI_PRE_REVIEW_REPORT.md`.

Status: **BLOCKED FROM AUTOMATIC USE pending governed source repair and
event consolidation**. Do not change production data or calculation
eligibility from this observation alone.

## Required next step

Use `RC030_C7_OWNER_VS_AI_COMPARISON_REPORT.md` to run a correction-only
owner mini-batch for ten substantive disagreements, decide the governed
equivalence of the eight table-aware labels, and repair/revalidate
`regimen_id=6068`. Existing owner events remain immutable.
