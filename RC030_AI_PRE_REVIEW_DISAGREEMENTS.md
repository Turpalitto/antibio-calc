# RC-030 AI Pre-Review — Disagreements with Parser Candidate

16 of 60 records where the independently-determined AI verdict disagrees with the parser's stored `parser_semantic_type`. Full evidence for each below.

## regimen_id=6657 (category C, confidence LOW_AMBIGUOUS)
- **PDF/page**: Повреждение связок коленного сустава.pdf p.26
- **Quote**: `цефуроксим** 50 мг/кг`
- **Parser candidate**: WEIGHT_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Quote "цефуроксим** 50 мг/кг" has no per-day or per-dose marker at all. Calibration record — matches owner verdict exactly.

## regimen_id=6659 (category C, confidence LOW_AMBIGUOUS)
- **PDF/page**: Повреждение связок коленного сустава.pdf p.26
- **Quote**: `ванкомицин** 15 мг/кг`
- **Parser candidate**: WEIGHT_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Same page/pattern as 6657: "ванкомицин** 15 мг/кг" has no explicit temporal marker.

## regimen_id=6658 (category C, confidence LOW_AMBIGUOUS)
- **PDF/page**: Повреждение связок коленного сустава.pdf p.26
- **Quote**: `#клиндамицин** 10 мг/кг`
- **Parser candidate**: WEIGHT_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Same page/pattern: "#клиндамицин** 10 мг/кг" has no explicit temporal marker.

## regimen_id=6653 (category C, confidence LOW_AMBIGUOUS)
- **PDF/page**: Повреждение связок коленного сустава.pdf p.26
- **Quote**: `ванкомицин** по 15 мг/кг в виде медленной в/в инфузии`
- **Parser candidate**: WEIGHT_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Quote "ванкомицин** по 15 мг/кг в виде медленной в/в инфузии" states route/infusion detail but no per-day or per-dose marker.

## regimen_id=5374 (category B, confidence MEDIUM_CONTEXTUAL)
- **PDF/page**: Врожденная нейтропения (ВН).pdf p.20
- **Quote**: `2. Азитромицин** 10 мг/кг/сут 1 раз в день – 3 раза в неделю;`
- **Parser candidate**: WEIGHT_PER_DAY
- **AI proposed verdict**: WRONG_FREQUENCY_LINK
- **Evidence explanation**: Quote "10 мг/кг/сут 1 раз в день – 3 раза в неделю" explicitly states "/сут" for the per-administration-day amount, but the regimen is intermittent (3x/week, not daily); the stored frequency field (1.0) does not capture the weekly periodicity, so the record risks being misread as daily.
- **Risk flags**: stored frequency=1.0 does not represent "3 раза в неделю"; sub-weekly periodicity lost

## regimen_id=6651 (category B, confidence LOW_AMBIGUOUS)
- **PDF/page**: Повреждение связок коленного сустава.pdf p.26
- **Quote**: `цефуроксим** 1,5 г`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Quote "цефуроксим** 1,5 г" — same marker-less prophylaxis-list pattern as regimen 6657 (calibration record), on the same page.
- **Risk flags**: mirrors the calibration record's exact ambiguity pattern

## regimen_id=6652 (category B, confidence LOW_AMBIGUOUS)
- **PDF/page**: Повреждение связок коленного сустава.pdf p.26
- **Quote**: `#клиндамицин** 900 мг`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Quote "#клиндамицин** 900 мг" — same marker-less pattern as 6657.
- **Risk flags**: mirrors the calibration record's exact ambiguity pattern

## regimen_id=6655 (category B, confidence LOW_AMBIGUOUS)
- **PDF/page**: Повреждение связок коленного сустава.pdf p.26
- **Quote**: `#левофлоксацин** 500 мг`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Quote "#левофлоксацин** 500 мг" — same marker-less pattern as 6657.
- **Risk flags**: mirrors the calibration record's exact ambiguity pattern

## regimen_id=6654 (category B, confidence LOW_AMBIGUOUS)
- **PDF/page**: Повреждение связок коленного сустава.pdf p.26
- **Quote**: `ципрофлоксацин** 400 мг`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Quote "ципрофлоксацин** 400 мг" — same marker-less pattern as 6657.
- **Risk flags**: mirrors the calibration record's exact ambiguity pattern

## regimen_id=5450 (category B, confidence HIGH_EXPLICIT)
- **PDF/page**: Урогенитальный трихомониаз.pdf p.14
- **Quote**: `тинидазол 2,0 г однократно`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: CORRECT_FIXED_SINGLE
- **Evidence explanation**: Quote "тинидазол 2,0 г однократно" — "однократно" (one-time-only) is an explicit, unambiguous single-administration marker; parser labeled it FIXED_PER_DAY, a type mismatch for a true one-time dose.
- **Risk flags**: parser type FIXED_PER_DAY mismatches an explicitly single/one-time regimen

## regimen_id=5895 (category B, confidence HIGH_EXPLICIT)
- **PDF/page**: Урогенитальный трихомониаз.pdf p.14
- **Quote**: `тинидазол 2,0 г однократно`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: CORRECT_FIXED_SINGLE
- **Evidence explanation**: Duplicate of 5450: "тинидазол 2,0 г однократно".
- **Risk flags**: parser type FIXED_PER_DAY mismatches an explicitly single/one-time regimen

## regimen_id=5913 (category B, confidence HIGH_EXPLICIT)
- **PDF/page**: Хламидийная инфекция.pdf p.21
- **Quote**: `азитромицин** 1,0 г однократно`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: CORRECT_FIXED_SINGLE
- **Evidence explanation**: Quote "азитромицин** 1,0 г однократно" — same "однократно" marker.
- **Risk flags**: parser type FIXED_PER_DAY mismatches an explicitly single/one-time regimen

## regimen_id=6976 (category B, confidence HIGH_EXPLICIT)
- **PDF/page**: Острый пиелонефрит.pdf p.32
- **Quote**: `Ципрофлоксацин**
500 мг 2 р/сут
7–10`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: CORRECT_FIXED_SINGLE
- **Evidence explanation**: Quote "Ципрофлоксацин** 500 мг 2 р/сут" — "2 р/сут" is an abbreviation of "2 раза в сутки" (twice daily), a per-dose+frequency marker; parser labeled it FIXED_PER_DAY, likely because the abbreviated "р/сут" form was matched as a plain per-day marker instead of being recognized as an abbreviated per-dose-frequency compound.
- **Risk flags**: likely real parser regex gap: abbreviated "р/сут" not recognized as per-dose marker (spelled-out "раза в сутки" elsewhere IS recognized correctly, e.g. regimen 5897/5905)

## regimen_id=7025 (category B, confidence HIGH_EXPLICIT)
- **PDF/page**: Острый пиелонефрит.pdf p.32
- **Quote**: `Ципрофлоксацин**
500 мг 2 р/сут
7–10`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: CORRECT_FIXED_SINGLE
- **Evidence explanation**: Duplicate of 6976: "500 мг 2 р/сут".
- **Risk flags**: likely real parser regex gap: abbreviated "р/сут" not recognized as per-dose marker

## regimen_id=5961 (category B, confidence LOW_AMBIGUOUS)
- **PDF/page**: Роды одноплодные, родоразрешение путем кесарева сечения.pdf p.54
- **Quote**: `Цефазолин**
1 г
внутривенно медленно`
- **Parser candidate**: FIXED_PER_DAY
- **AI proposed verdict**: REMAINS_AMBIGUOUS
- **Evidence explanation**: Quote "Цефазолин** 1 г внутривенно медленно" — no per-day or per-dose marker in the captured quote (cesarean prophylaxis, typically single perioperative dose, but not stated explicitly here).

## regimen_id=7354 (category B, confidence HIGH_EXPLICIT)
- **PDF/page**: Хламидийная лимфогранулёма (венерическая).pdf p.18
- **Quote**: `Доксициклин** 100 мг внутрь дважды в день в течение 21 дня.`
- **Parser candidate**: AMBIGUOUS
- **AI proposed verdict**: CORRECT_FIXED_SINGLE
- **Evidence explanation**: Quote "100 мг внутрь дважды в день" — "дважды в день" (twice a day) is an explicit per-dose marker; parser labeled this AMBIGUOUS, likely because its frequency-marker pattern recognizes "N раз(а)" but not the single-word "дважды".
- **Risk flags**: likely real parser regex gap: "дважды" (twice) not recognized where "2 раза"/spelled forms are
