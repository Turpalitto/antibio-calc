# RC-030 Range Rebuild — Integrity Report

Experimental artifact: `generated/rc030_range_rebuild/assembled_regimens_range_v2.sqlite` (non-authoritative; gitignored as `*.sqlite` and under `generated/`).

- Rows total: 2675
- Rows with a range recovered from source_quote: 365
- **Authoritative DBs unchanged (sha256 before==after): True**

## Structural integrity (experimental vs authoritative)

- Rows compared: 2675
- Clinical-field violations (antibiotic/dose/unit/frequency/route/duration/diagnosis/source_quote/status/approval): **0**
- Rows added: 0; rows dropped: 0
- **Only range fields differ: True**

## CRITICAL LIMITATION — range-to-scalar attribution

The range recovery uses a simple *first true numeric range in `source_quote`* heuristic. On a multi-drug quote this can attach a range that belongs to a **different** drug/dose than the row's structured scalar. Split of the 365 recovered rows:

- **186 rows (51%): trustworthy** — recovered lower bound == the structured scalar dose (the range clearly belongs to this row).
- **179 rows (49%): SUSPECT** — recovered lower bound != structured scalar, i.e. the first range in the quote likely belongs to a neighbouring drug. Example: regimen 5622 has scalar 15 mg/kg but the first quote range is `0,6-0,9 г` (a different drug's fixed dose).

**Consequence:** the experimental artifact's `dose_max` is only reliable for the trustworthy subset; the suspect subset needs span-linked recovery (anchor the range to the same dose token, as the sandbox parser's `range_collapsed_upstream` guard already does) before any use. Every recovered row — trustworthy or suspect — still requires owner review and remains calculation BLOCKED. This is why the authoritative migration (Phase 22) is gated behind span-linked re-derivation, not this naive manifest.

## Sample of trustworthy rows (scalar == recovered lower bound)

| regimen | scalar / min | recovered max | evidence |
|---|---|---|---|
| 5623 | 0.6 | 0.9 | 0,6-0,9 г |
| 5628 | 0.6 | 0.9 | 0,6-0,9 г |
| 5659 | 1.0 | 2.0 | 1–2 г |
| 5660 | 20.0 | 50.0 | 20–50 мг |
| 5661 | 20.0 | 80.0 | 20–80 мг |
| 5671 | 500.0 | 1000.0 | 500 - 1000 мг |
| 5683 | 50.0 | 80.0 | 50-80 мг |
| 5677 | 100.0 | 200.0 | 100-200 мг |
| 5678 | 20.0 | 80.0 | 20-80 мг |
| 5688 | 250.0 | 500.0 | 250 – 500 мг |
| 5696 | 10.0 | 20.0 | 10-20 мг |
| 6561 | 20.0 | 60.0 | 20-60 мг |
| 5727 | 10.0 | 20.0 | 10-20 мг |
| 5741 | 20.0 | 30.0 | 20-30 мг |
| 5793 | 0.2 | 0.4 | 0,2–0,4 г |

## Sample of SUSPECT rows (scalar != recovered lower bound — do NOT trust dose_max)

| regimen | scalar | recovered min | recovered max | evidence |
|---|---|---|---|---|
| 5584 | 1.0 | 0.5 | 1.0 | 0,5–1,0 г |
| 5620 | 1.0 | 2.0 | 3.0 | 2,0-3,0 г |
| 5621 | 1.5 | 2.0 | 3.0 | 2,0-3,0 г |
| 5622 | 15.0 | 0.6 | 0.9 | 0,6-0,9 г |
| 5624 | 1.0 | 2.0 | 3.0 | 2,0-3,0 г |
| 5625 | 1.5 | 0.5 | 1.0 | 0,5-1,0 г |
| 5627 | 15.0 | 0.6 | 0.9 | 0,6-0,9 г |
| 5686 | 1000.0 | 250.0 | 500.0 | 250 – 500 мг |
| 5687 | 1000.0 | 250.0 | 500.0 | 250 – 500 мг |
| 5697 | 50.0 | 10.0 | 20.0 | 10-20 мг |
| 5698 | 20.0 | 10.0 | 20.0 | 10-20 мг |
| 6562 | 625.0 | 20.0 | 60.0 | 20-60 мг |
| 5726 | 1.0 | 0.5 | 1.0 | 0,5-1,0 г |
| 5742 | 30.0 | 20.0 | 30.0 | 20-30 мг |
| 5745 | None | 60.0 | 80.0 | 60 до 80 мг |