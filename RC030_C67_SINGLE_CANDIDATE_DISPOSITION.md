# RC-030 / C6.7 Part VI — 43 SAFE_SINGLE_CANDIDATE Disposition

Per the owner's explicit instruction, `SAFE_SINGLE_CANDIDATE` is **not** migration-safe under any circumstance. This audit classifies why each of the 43 fell short of exact-link admission and whether it needs owner confirmation, table review, or is blocked outright. No record is promoted to exact-link in this pass — no deterministic rule change is applied without its own commit and regression tests, per the owner's explicit prohibition on relaxing rules to reduce workload.

## Disposition summary

| Disposition | Count |
|---|---|
| SINGLE_REQUIRES_SIMPLE_OWNER_CONFIRMATION | 26 |
| SINGLE_REQUIRES_TABLE_REVIEW | 8 |
| SINGLE_SOURCE_BLOCKED | 2 |
| SINGLE_NOT_A_RANGE | 2 |
| SINGLE_REQUIRES_ALTERNATIVE_REVIEW | 2 |
| SINGLE_WRONG_ANCHOR | 2 |
| SINGLE_REQUIRES_PHASE_SPLIT | 1 |
| SINGLE_DICTIONARY_CONFIRMATION | 0 |
| **Total** | **43** |

Full per-record mapping: `generated/rc030_c67/single_candidate_disposition.json`.

## SINGLE_REQUIRES_SIMPLE_OWNER_CONFIRMATION (26)

Pass A independently agreed the range plausibly links to the named antibiotic (`INDEPENDENT_EXACT_LINK` or `INDEPENDENT_SINGLE_PLAUSIBLE`), the engine's own multi-drug/ambiguity signal is why it stopped short of exact-link (not a genuine defect found by this audit), and no PDF/unit-basis issue was found. These are the most owner-review-ready of the 43 — a single yes/no confirmation against the source quote should resolve each.

## SINGLE_REQUIRES_TABLE_REVIEW (8)

`5623, 5628, 6756, 6761, 6766, 6771, 6799, 6804` — Pass A independently identified these as flattened prophylaxis-dosing table rows (drug/dose/timing/route concatenated with ellipses or column breaks, no connecting prose), even though the engine's own table-context flag was never triggered for any of them. Per Phase 10, table-derived records require row/column/header provenance (DocLayout-YOLO/Table Transformer/PyMuPDF-block-coordinate reconstruction) before any confirming verdict is possible — **not attempted in this pass**, since no ML table-layout tooling is installed in this environment. These 8 need that tooling (or careful manual table-structure review) before they can even reach a confirmation-ready state.

## SINGLE_SOURCE_BLOCKED (2)

`5688, 6052` — per the PDF/table evidence audit (Part VII), both cite `Острый гепатит В (ГВ) у взрослых.pdf` page 42, but the quoted text (cefazolin/ceftriaxone + metronidazole antibacterial coverage) does not appear anywhere in that 75-page document. This is a source-attribution defect upstream of this audit, not a table or ambiguity issue — these two cannot be confirmed against their cited source at all and must be re-sourced (or re-attributed to the correct guideline) before any further review is meaningful.

## SINGLE_REQUIRES_ALTERNATIVE_REVIEW (2)

`6638, 5514` — flagged by the unit-normalization audit (Part VIII) as a `mg` (absolute) vs `mg/kg` (per-weight) dose-basis mismatch between the DB's `structured_unit` and the text's captured range unit. Pass A independently rated both `INDEPENDENT_SINGLE_PLAUSIBLE` (not a rejection, but not clean either). These need a reviewer to determine, by reading the surrounding sentence structure, which basis the source text actually intends — the engine's captured `unit_raw` cannot be trusted here for the same reason documented for the 6 high-severity exact-link downgrades.

(Note: two further `SAFE_SINGLE_CANDIDATE` records, `6110` and `6111`, carry a *low-severity* unit-annotation gap — g vs г/сут, same substance, no weight-basis conflation — and were left in `SINGLE_REQUIRES_SIMPLE_OWNER_CONFIRMATION` rather than escalated, since the underlying quantity is not actually in dispute.)

## SINGLE_WRONG_ANCHOR (2)

`5526, 5533` — both cite Кларитромицин (clarithromycin) with structured_dose 500mg, but Pass A found the quote's only numeric range (15-20 мг/кг) structurally belongs to a *different* drug (этамбутол/ethambutol) mentioned in the same multi-drug sentence; clarithromycin itself only has a scalar dose (500 мг 2 раза в сутки) in the quote, no range at all. **This is a genuine wrong-anchor risk** — if ever migrated, these would attach ethambutol's per-kilogram range to clarithromycin's record.

## SINGLE_NOT_A_RANGE (2)

`5528, 6072` — Pass A found no true dose range for the named drug in either quote: `5528` (рифабутин) has only a scalar "5 мг/кг 1 раз в сутки"; `6072`'s target drug has only a scalar "1000 мг 3 раза в сутки" with a range present elsewhere in the quote for a different context/drug basis (also separately flagged for the unit-basis issue in Part VIII). Neither should be treated as a dose-range candidate at all, regardless of confirmation.

## SINGLE_REQUIRES_PHASE_SPLIT (1)

`5726` — цефазолин (cefazolin) quote contains a scalar "1,0г" immediately adjacent to a comma-separated range "0,5-1,0 г", with the same range appearing a second time in a different clause of the same quote. This reads as a loading/maintenance or repeated-context structure that needs to be split into distinct phases before any single verdict (confirm or reject) is meaningful — a single yes/no confirmation would conflate two distinct clinical statements.

## Promotion-to-exact-link assessment

No deterministic evidence improvement is proposed for promoting any of the 43 to exact-link in this pass. The `SINGLE_REQUIRES_SIMPLE_OWNER_CONFIRMATION` 26 are the closest to promotable, but promotion requires human confirmation against source (an owner-review event), not a rule change — per the owner's explicit standard, a concrete deterministic rule plus a regression test plus full 365-record replay plus adversarial-corpus proof would be required to promote any record by rule change alone, and no such rule was found or proposed here.
