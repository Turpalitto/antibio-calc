# RC030_12CASE_REVALIDATION.md

Status: RC-030 Evidence Validation, Phase 6. Full re-read of every one of the 12 original pilot
cases against complete `source_quote` text, independently of the classifier's own output, plus a
dedicated analysis of regimen 5574 (the illustrative example cited elsewhere, not one of the formal
12 — addressed separately per explicit instruction). Re-run after the two Phase 4/6 fixes
(`dose_token_located` guard, `SUB_DAILY_FREQUENCY` block).

## The 12 original pilot cases

| # | regimen_id | antibiotic | dose/unit/freq | semantic_type | evidence | calc_status | daily / single (mg) |
|---|---|---|---|---|---|---|---|
| 1 | 5364 | Пиперациллин+тазобактам | 250 mg/kg, freq=3 | WEIGHT_PER_DAY | `"250 – 300 мг/кг/сут в 3-4 приема"` — explicit `/сут` | OK | 4500 / 1500 |
| 2 | 5376 | Ко-тримоксазол | 5 mg/kg, freq=**3/7≈0.4286** | WEIGHT_PER_DAY | `"5 мг/кг/сут в два/три приема – 3 раза в неделю"` — explicit `/сут`, **but dosed 3×/week, not daily** | **BLOCKED** (`SUB_DAILY_FREQUENCY`) | — |
| 3 | 5377 | Азитромицин | 10 mg/kg, freq=1 | WEIGHT_PER_DAY | `"10 мг/кг/сут 1 раз в день – 3 раза в неделю"` — explicit `/сут`; freq=1 stored (daily-equivalent) | OK | 180 / 180 |
| 4 | 5378 | Амоксициллин/клавуланат | 40 mg/kg, freq=2 | WEIGHT_PER_DAY | `"40 мг/кг/сутки в два приема - ежедневно"` — explicit `/сутки`, **explicit "ежедневно" (daily) confirms true daily dosing**, unlike case 2 | OK | 720 / 360 |
| 5 | 5439 | Азитромицин | 20 mg/kg, freq=1 | WEIGHT_PER_DAY | `"20 мг на кг массы тела в сутки 1 раз в сутки"` — doubly explicit | OK | 360 / 360 |
| 6 | 5355 | Цефиксим | 400 mg, freq=1 | FIXED_PER_DOSE | `"400 мг (1 раз в сутки или по 200 мг 2 раза в сутки)"` — explicit | OK | 400 / 400 |
| 7 | 5356 | Цефиксим | 200 mg, freq=2 | FIXED_PER_DOSE | same sentence, second alternative — explicit | OK | 400 / 200 |
| 8 | 5400 | Кларитромицин | 500 mg, freq=2 | FIXED_PER_DOSE | `"кларитромицин** (500 мг 2 раза в сутки)"` — explicit, tight parens | OK | 1000 / 500 |
| 9 | 5401 | Амоксициллин | 1000 mg, freq=2 | FIXED_PER_DOSE | `"амоксициллин** (1000 мг 2 раза в сутки)"` — explicit, tight parens | OK | 2000 / 1000 |
| 10 | 5402 | Тетрациклин | 500 mg, freq=4 | FIXED_PER_DOSE | `"#тетрациклином (500 мг 4 раза в сутки)"` — explicit, tight parens | OK | 2000 / 500 |
| 11 | 6275 | Пиперациллин+тазобактам | 4.5, unit=`"г; мг/кг"` | UNPARSED | compound/duplicated unit string — genuine source defect | BLOCKED | — |
| 12 | 6405 | Пиперациллин+тазобактам+амикацин | 4.5, unit=`"г; мг/кг/сут; мг/кг/сут"` | UNPARSED | compound/duplicated unit string — genuine source defect | BLOCKED | — |

**10/12 manually confirmed CORRECT as classified. 1/12 (case 2, regimen 5376) is a genuine
calculation-safety bug, found by this manual re-read, not by the classifier or the earlier automated
risk audit** — the `/сут` signal is textually correct (the dose really is per-day), but the stored
`frequency=3/7` represents weekly periodicity, not intra-day administration count, and applying
`single = daily ÷ frequency` produced a physically impossible result (single dose > daily dose). Now
**fixed**: `calculator.py` blocks any calculation where `frequency < 1` with a `SUB_DAILY_FREQUENCY`
warning, rather than silently producing an impossible number. 2/12 (cases 11, 12) correctly remain
blocked as genuinely unparseable compound units — unchanged from the original P5.6 pilot.

**Contrast worth noting**: case 2 (5376, blocked) and case 4 (5378, OK) look superficially similar
(`"N мг/кг/сут(ки) в M приема"`), but case 4's text adds `"ежедневно"` (daily) confirming true daily
dosing, while case 2's text adds `"3 раза в неделю"` (3×/week) — a real, source-text-backed
distinction that the fix now respects by refusing the arithmetic rather than assuming either reading.

## Regimen 5574 — definitive analysis (per explicit instruction)

**Not one of the formal 12-case pilot** (`data/pilot_report.json` lists 5364, 5376, 5377, 5378, 5439,
5355, 5356, 5400, 5401, 5402, 6275, 6405) — it was cited separately, as an illustrative worked example
in `DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md`. Addressed here specifically because the instruction
names it explicitly.

**Correction (see `ROOT_CAUSE_REGISTER.md` — RC-031 retracted):** an earlier version of this section,
and of `DOSE_SANDBOX_RC030_INTEGRATION_REPORT.md`, incorrectly labeled this regimen's antibiotic as
"Азитромицин" and quoted a fabricated `source_quote` string built by hand rather than copied from the
database. The actual, verified (live-queried, hash-confirmed) `assembled_regimens.sqlite` row is
reproduced exactly below.

```
regimen_id: 5574
diagnosis: A63.8 (Урогенитальные заболевания, вызванные M. genitalium, у детей с массой тела менее 45 кг)
antibiotic: джозамицин
dose: 50.0   unit: mg/kg   frequency: 2.0   age_group: child
source_pdf: Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf, page 16
source_quote (full, verbatim, copied from the live database):
  "Рекомендовано  для лечения детей с массой тела менее 45 кг назначать перорально
   джозамицин** 50 мг на кг массы тела в сутки, разделённые на 2 приема, в течение 10
   дней"
```

**Question asked**: does the source mean (a) 50 mg/kg/day divided into 2 doses, or (b) 50 mg/kg/dose
given twice daily?

**Answer: (a) — 50 mg/kg/day, divided into 2 doses. This is explicit in the source text, not
inferred.** Two independent textual markers both confirm this, not one:

1. `"...массы тела в сутки"` — "per day" directly modifies the 50 mg/kg figure.
2. `", разделенные на 2 приема,"` — "divided into 2 doses" — explicitly states that the just-stated
   daily quantity is what gets split across 2 administrations, not that 50 mg/kg is itself repeated
   twice.

This is a stronger evidentiary case than most of the corpus: two independent, non-overlapping phrases
in the same sentence both point to the same reading, with no competing signal anywhere in the quote
(the quote is a single, self-contained sentence about only this drug — no `"или"`, no other drug name,
no other numeric dose). **`semantic_type = WEIGHT_PER_DAY` is correct, not merely
"algebraically convenient."**

Calculation (weight 18 kg, representative pediatric weight used elsewhere in this validation):

```
daily = 50 × 18 = 900 mg/day
single = 900 ÷ 2 = 450 mg/dose
calculation_status: OK
```

If the alternative reading (b) had been correct instead, the numbers would be: single = 50 × 18 = 900
mg/dose, daily = 900 × 2 = 1800 mg/day — a **2× difference**, which is exactly why this distinction
matters clinically and why RC-030 exists. The source text itself resolves it unambiguously in this
case.
