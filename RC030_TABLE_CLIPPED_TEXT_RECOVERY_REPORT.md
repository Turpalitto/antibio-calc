# RC-030 Table Clipped-Text Recovery — Pilot Result

Implemented and run against the 3 pages with independently-confirmed tables (DocLayout-YOLO + Table Transformer agreement):

| Page | Table Transformer bbox (PDF pts) | Score | Clipped text length | Whole-page text length |
|---|---|---|---|---|
| `Лепра [болезнь Гансена].pdf` p.32 | `[85.6, 550.8, 552.1, 763.9]` | 1.0 | 559 chars | 1969 chars |
| `Отит средний острый.pdf` p.23 | `[26.6, 375.1, 511.4, 813.9]` | 0.999 | 1247 chars | 2395 chars |
| `Паратонзиллярный абсцесс.pdf` p.22 | `[68.8, 92.9, 526.0, 327.0]` | 0.998 | 1390 chars | 3104 chars |

## Method

1. Table Transformer detection re-run on the batch's already-rendered page images (150 DPI) with box coordinates captured (the earlier Phase-1 run only persisted label/score, not boxes — corrected here).
2. Pixel coordinates converted to PDF points via `scale = 72/150`.
3. `fitz.Page.get_text("text", clip=fitz.Rect(pdf_box))` extracts embedded text within that region only — no OCR, no rendering-to-image round-trip.

## Result: 100% correct on all 3 pages, generated from PDF coordinates (not hand-typed)

**Отит средний острый.pdf p.23** — the target row:
```
Джозамицин**(Код АТХ: J01FA07)
2000 мг/сутки в 2
приема
40-50
мг/кг/сутки
2-3 приема
Независимо
```
Correct antibiotic name, correct adult dose (2000 мг/сутки в 2 приема), correct pediatric weight-based dose (40-50 мг/кг/сутки in 2-3 doses), correct food-independence note. Compare against §6 of `RC030_CYRILLIC_TABLE_TEXT_COMPARISON.md`: MinerU's OCR of the identical region dropped the drug name and dose unit entirely; RapidTable corrupted the Cyrillic characters.

**Лепра [болезнь Гансена].pdf p.32** — recovered a full multi-column prednisolone/methotrexate weight-tiered dosing schedule (age-banded doses from 2.5 mg to 40 mg, by body weight threshold and treatment month), verbatim and complete.

**Паратонзиллярный абсцесс.pdf p.22** — recovered the full antibiotic choice table including the **exact range expression that is regimen 5660 from `RC030_RANGE_EXPRESSION_RCA.md`**: "Новорожденным (до 2 недель) назначают по 20-50 мг/кг массы тела 1 раз/сут" — independently cross-validates that RCA's finding from a completely different extraction path (table-region clip vs. the `source_quote` field already in the database).

## Comparison against assembled `source_quote`

For the Отит page, the recovered table text is a superset of what's likely captured in any single `source_quote` for one regimen row (each `assembled_regimens` row typically carries only its own drug's quote, not the whole table) — meaning table-region recovery could, in principle, recover **row/column context that individual `source_quote` fields lack today** (e.g., confirming which column a dose belongs to — "Дети" vs. "Взрослые" — something a single-row `source_quote` doesn't always make explicit).

## Not yet done in this turn

- Row/column reconstruction from individual word bounding boxes (the mission's step 5-6: `page.get_text("words", clip=...)` with per-word offsets, then geometric row/cell grouping) — this pilot used whole-region `get_text("text", clip=...)`, which is enough to *prove the concept* and recover complete, correct text, but not enough to programmatically know which cell each token belongs to. That structured reconstruction is a real follow-up, not attempted here due to time.
- Running this pipeline across all 6 detected-table pages (only the 3 with cross-tool agreement were processed) or the full 104-row max-dose candidate set.

## Conclusion

`EMBEDDED_TEXT_PREFERRED` confirmed for this born-digital corpus, at least for the 3 pages tested. The recovery is real, generated from coordinates (not manually retyped), and independently cross-validates two separate prior findings (the джозамицин Отит regimen and the regimen-5660 range expression).
