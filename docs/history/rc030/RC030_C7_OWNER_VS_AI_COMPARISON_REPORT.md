# RC-030 C7 Owner vs AI Comparison Report

Date: 2026-07-30

## Final corrected outcome

After intake of all superseding owner corrections:

| Final result | Count |
|---|---:|
| Exact owner/AI canonical-verdict match | 105 |
| Same per-administration basis, table-aware label difference | 8 |
| Quarantined extraction defect | 0 |
| Remaining substantive owner/AI disagreement | 0 |
| Total | 113 |

The final append-only history contains 182 events and exactly one terminal
event for each of 113 regimens. Validation returned zero issues.
The repaired `6068` evidence now terminates in `CORRECT_RANGE_SINGLE` and
exactly matches the independent AI source-fidelity verdict.

Final artifacts:

- `%USERPROFILE%\Downloads\RC030_C7_FINAL_2026-07-30\RC030_C7_FINAL_OWNER_EVENTS_2026-07-30.json`
  - SHA-256:
    `1A54B24F55A2677402246486F0624ACA8E3CA716B28C29EB025B4BF7AF86D885`
- `%USERPROFILE%\Downloads\RC030_C7_FINAL_2026-07-30\RC030_C7_FINAL_COMPARISON_2026-07-30.json`
  - SHA-256:
    `2214A211E98D6206CDC76E4927EF6A1354A44EFAF8C5EA2BF51035763C57D80C`

The earlier comparison sections below document the pre-correction state and
remain as audit history.

Scope: source-fidelity classification only. This report is not a treatment
recommendation, clinical approval, or permission to connect the Clinical
Engine.

## Intake result

- owner event history: 157 append-only events;
- unique reviewed regimens: 113/113;
- schema/identity/supersession validation issues: 0;
- every regimen has exactly one terminal owner event;
- 11 per-batch exports and one consolidated export were preserved under
  `%USERPROFILE%\Downloads\RC030_C7_owner_exports_2026-07-30T05-33-36-881Z`.

## Comparison result

| Result | Count |
|---|---:|
| Exact canonical-verdict match | 94 |
| Same dose basis, different confirming label | 8 |
| Substantive owner/AI disagreement | 10 |
| Confirmed extraction defect requiring quarantine | 1 |
| Total | 113 |

The eight label-only differences are records `5623`, `5628`, `6756`, `6761`,
`6766`, `6771`, `6799`, and `6804`. The owner selected
`CORRECT_EXPLICIT_PER_DOSE` from the table-aware action; AI selected
`CORRECT_RANGE_SINGLE`. Visual review of pages 24-25 of
`Перелом нижней челюсти.pdf` confirms that both describe the same
per-administration prophylaxis range `0.6-0.9 g` for clindamycin. Do not
rewrite either immutable event automatically; any metric-level equivalence
must be an explicit governed normalization rule.

## Substantive disagreements checked against rendered PDF pages

| Regimen | Owner | Source-based result | Reason |
|---:|---|---|---|
| 6296 | daily range | per-administration range | The PDF explicitly says `Разовые дозы`; cefazolin is `30-50 mg/kg` per dose. |
| 6550 | daily range | per-administration range | Same explicit `Разовые дозы` wording in the second fracture guideline. |
| 5475 | daily range | per-administration range | `25-50 mg/kg` is followed by frequency `1 раз в сутки`; frequency does not change the range into a daily-total basis. |
| 5478 | daily range | per-administration range | The PDF says `однократно`. |
| 5441 | wrong drug anchor | daily range for erythromycin | The paragraph explicitly introduces intravenous erythromycin and gives `20-40 mg/kg ... в сутки`; the numbers are linked to erythromycin. |
| 7519 | per-administration range | daily-total range | The unit is explicitly `mg/kg/сутки`. |
| 7629 | per-administration range | daily-total range | Duplicate source statement; the unit is explicitly `mg/kg/сутки`. |
| 7644 | per-administration range | daily-total range | Duplicate source statement; the unit is explicitly `mg/kg/сутки`. |
| 5528 | per-administration range for rifabutin | wrong dose anchor | The highlighted `15-20 mg/kg` belongs to ethambutol; rifabutin is `5 mg/kg once daily`. |
| 5824 | daily range | per-administration range | `10-20 mg/kg` is followed by the administration frequency `1 or 2 times/day`; `/day` modifies the frequency, not the dose unit. |

For these ten records, the independent AI verdict matches the visually
verified source. The existing owner events remain immutable; corrections
must be new superseding owner events, never hand-edits.

## Extraction defect 6068

The owner note and independent AI visual review identified the same defect:
the PDF shows amoxicillin `500¹-1000² mg 3 times daily`, while extraction
flattened superscript footnote markers into `5001-10002 mg`.

The terminal owner label `WRONG_FREQUENCY_LINK` does not describe the actual
defect, and the AI label `CORRECT_RANGE_SINGLE` alone does not repair the
corrupted source text. Keep regimen `6068` quarantined until:

1. the source extraction is repaired to numeric range `500-1000 mg`;
2. the repaired record is revalidated;
3. the owner records a new superseding verdict against the repaired evidence.

## Governance status

The exports are valid review evidence, but no owner event has been converted
into clinical approval or calculation eligibility. P5.6 remains
ACCEPTANCE/NOT COMPLETE until the ten substantive corrections, the eight-label
normalization decision, and the `6068` governed repair are resolved. P6
remains BLOCKED.
