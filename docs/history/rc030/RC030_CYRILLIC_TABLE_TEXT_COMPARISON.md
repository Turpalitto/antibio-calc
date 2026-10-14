# RC-030 Cyrillic Table-Text Comparison — Embedded Text vs. OCR

Compared four independent extractions of the same table (`Отит средний острый.pdf` p.23, Table 4 — "Суточные дозы и режим введения антибиотиков при ОСО") on the same page, same render.

## Ground truth (source PDF has an embedded text layer, not a scan)

**PyMuPDF, region-clipped** (Table Transformer bbox → PDF coordinates → `page.get_text("text", clip=rect)`): **100% correct, complete Cyrillic**, including the target row:
```
Джозамицин**(Код АТХ: J01FA07)
2000 мг/сутки в 2
приема
40-50
мг/кг/сутки
2-3 приема
Независимо
```

## OCR-based extractions of the identical table region

**MinerU** (batch run, `page07.md`) — **worse than character corruption: entire tokens are dropped.** The Джозамицин row renders as:
```
<td>( : 0107)</td><td>2000 /  2</td><td>40-50 //2-3 </td>
```
The antibiotic name "Джозамицин\*\*" is **completely absent** from the cell (not misspelled — empty). The dose unit "мг/кг/сутки" is also dropped entirely ("40-50 // 2-3" instead of "40-50 мг/кг/сутки 2-3 приема") — the numbers survive, the unit does not.

**RapidTable** (same page, whole-page structure recognition) — character-level corruption rather than token loss, but still wrong: `90 /κ/cyτ B 3` instead of `90 мг/кг/сут в 3`, `2,0-4,0 r/cyT B 1` instead of `2,0-4,0 г/сут в 1`. Cyrillic к/т/г/в consistently confused with Latin/Greek look-alikes (κ, τ, r, B).

**MinerU, single-page smoke test** (`page16.md` from the earlier regimen-5574 smoke run, different page but same OCR pipeline) showed the same character-substitution pattern as RapidTable rather than the batch run's token-dropping — i.e., **MinerU's failure mode is not even consistent across runs of the same tool**, which is itself worth noting: OCR-table-cell output on this corpus is not just wrong, it's *unpredictably* wrong.

## Classification (per mission's allowed result set)

**`EMBEDDED_TEXT_PREFERRED`** for all three pages tested. No page in this pilot produced a case where OCR text was more complete or more accurate than the embedded-text-plus-bbox-clip approach — because every PDF checked in this corpus is born-digital, not scanned.

## Recommendation

Do not use MinerU/RapidTable/Docling's OCR-driven table-cell text for this corpus's dosing extraction. Use the pattern demonstrated in this pilot: **layout/table detection for the region (DocLayout-YOLO or Table Transformer, both already proven reliable) → PyMuPDF `get_text(clip=...)` on that region in PDF-point coordinates → row/column reconstruction from word bounding boxes** (not implemented in this turn — see `RC030_TABLE_CLIPPED_TEXT_RECOVERY_REPORT.md` §"not yet done"). This would have recovered the Джозамицин 40-50 мг/кг/сутки pediatric row completely and correctly, where MinerU dropped it and RapidTable corrupted it.

`OCR_TEXT_PREFERRED` would only apply to a genuinely scanned (image-only) PDF, none of which have been encountered in this corpus so far — worth flagging that this recommendation may not generalize to the 68 PDFs not yet checked locally.
