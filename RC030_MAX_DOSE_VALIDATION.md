# RC030_MAX_DOSE_VALIDATION.md

Status: RC-030 Evidence Validation, Phase 8. Independent audit of all 26 max-dose values extracted
by `extract_max_dose_value_from_window` (R6, `RC030_RULE_CATALOG.md`) across the full corpus —
every single one, not a sample, since only 26 exist.

## Method

For each of the 26 rows (`dose_verification_sandbox/data/phase8_all_max_dose_extractions.json`),
manually verified against the full `source_quote`:

1. Does `"не более N мг"` belong to *this row's* regimen, or a neighboring drug in the same combined
   sentence?
2. Is daily-vs-single attribution explicit, or inferred from this row's own resolved period?
3. Is the maximum a genuine ceiling, or actually the upper bound of a dose range mislabeled as a max?
4. Is it from the correct age group?
5. Is there any table-header inheritance involved? (No — confirmed none of the 26 rows involve table
   structure; all are inline parenthetical statements.)

## Result: all 26 are correctly attributed on manual review

| Pattern | Count | Verdict |
|---|---:|---|
| `"X мг/кг (не более Y мг)"` — tight parenthetical, immediately adjacent to this row's own dose | 22 | Correct — e.g. regimen 5629 Гентамицин `"1,5 мг/кг (не более 120 мг)"`, regimen 7429 Амоксициллин `"50 мг/кг ... но не более 2 гр."` |
| `"X мг/кг массы тела (не более Y мг) ... 1 раз в сутки"` | 4 | Correct — e.g. regimen 5474/5476 Спектиномицин `"40 мг на кг массы тела (не более 2,0 г) внутримышечно однократно"` |

No case of: max belonging to a different drug, max from a different age group, a range upper bound
mislabeled as a max, or table-header inheritance (none of the 26 involve tables at all — all are
inline parenthetical statements in running text, which is exactly why R6's proximity-window scoping
was sufficient here).

## One consistency gap found (cosmetic, not numerically dangerous)

Regimens 5475 and 5478 — same drug (цефтриаксон), same dose (25-50 mg/kg), same cap (125 mg), nearly
identical source sentences — resolve to different attachment points: 5475's cap attaches to
`max_single_dose` (because its window matched `"1 раз в сутки"`, a per-dose R1 signal), while 5478's
attaches to `max_daily_dose` (because it resolved via the `RESOLVED_BY_FREQUENCY_ONE` shortcut
instead). **Since `frequency == 1` in both cases, `max_single_dose` and `max_daily_dose` are the same
number** (one administration per day), so this is a **labeling inconsistency, not a numeric error** —
flagged for cleanup, not a safety issue.

## Higher-risk case examined separately

Regimen 5657 (flagged `CROSSES_ALTERNATIVE_BOUNDARY` + `COMPETING_DOSE_NUMBER_BETWEEN` in Phase 3)
contains the phrase `"в дозах, не превышающих 2400/600 мг"` — genuine max-dose language, but for a
*combination-drug pair* (`2400/600`, two numbers), which R6's single-number regex correctly does
**not** match (it requires one plain number immediately after "не более"/"не превышающих"). Result:
no value was extracted for this row at all — the risky language exists in the quote, but R6 correctly
declined to guess which of the two numbers (or their combination) applies, rather than picking one
arbitrarily. This is the desired fail-safe behavior, confirmed by inspection.

## Conclusion

All 26 source-backed max-dose extractions currently in the corpus are correctly attributed to their
own regimen, on full (not sampled) manual review. This is a small population (26 of 2,675 rows,
1.0%), so this 100% result should not be read as a general precision guarantee for a hypothetically
larger max-dose-bearing corpus — it is a complete census of what exists today, not a sample estimate.
