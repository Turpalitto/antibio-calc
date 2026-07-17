# RC-030 Autonomous AI Audit — Parser Disagreements

Records where the blinded AI verdict does not endorse the parser classification. Two kinds: DISAGREE (AI confirms the opposite day/dose family) and AI_NONCONFIRMING (parser confirmed a family, AI returned ambiguous/table/frequency-error).

## DISAGREE

### 5450
- Quote: `тинидазол 2,0 г однократно`
- Parser: FIXED_PER_DAY  →  AI: CORRECT_FIXED_SINGLE
- Evidence: "однократно" = one-time single administration.

### 5895
- Quote: `тинидазол 2,0 г однократно`
- Parser: FIXED_PER_DAY  →  AI: CORRECT_FIXED_SINGLE
- Evidence: "однократно" (dup).

### 5913
- Quote: `азитромицин** 1,0 г однократно`
- Parser: FIXED_PER_DAY  →  AI: CORRECT_FIXED_SINGLE
- Evidence: "однократно".

### 6976
- Quote: `Ципрофлоксацин** 500 мг 2 р/сут 7–10`
- Parser: FIXED_PER_DAY  →  AI: CORRECT_FIXED_SINGLE
- Evidence: "2 р/сут" = twice daily; 500 mg is per administration.

### 7025
- Quote: `Ципрофлоксацин** 500 мг 2 р/сут 7–10`
- Parser: FIXED_PER_DAY  →  AI: CORRECT_FIXED_SINGLE
- Evidence: "2 р/сут" (dup).

### 7354
- Quote: `Доксициклин** 100 мг внутрь дважды в день в течение 21 дня.`
- Parser: AMBIGUOUS  →  AI: CORRECT_FIXED_SINGLE
- Evidence: "дважды в день" = twice daily; per administration.

## AI_NONCONFIRMING

### 6657
- Quote: `цефуроксим** 50 мг/кг`
- Parser: WEIGHT_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: No per-day/per-dose marker on the dose. CALIBRATION.

### 6659
- Quote: `ванкомицин** 15 мг/кг`
- Parser: WEIGHT_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: No temporal marker.

### 6658
- Quote: `#клиндамицин** 10 мг/кг`
- Parser: WEIGHT_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: No temporal marker.

### 6653
- Quote: `ванкомицин** по 15 мг/кг в виде медленной в/в инфузии`
- Parser: WEIGHT_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: Route/infusion detail only; no per-day/dose marker.

### 5374
- Quote: `2. Азитромицин** 10 мг/кг/сут 1 раз в день – 3 раза в неделю;`
- Parser: WEIGHT_PER_DAY  →  AI: WRONG_FREQUENCY_LINK
- Evidence: Dose basis explicit per-day, but schedule is 3x/week; normalized frequency=1 does not represent weekly periodicity.

### 6651
- Quote: `цефуроксим** 1,5 г`
- Parser: FIXED_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: No temporal marker (mirrors calibration pattern).

### 6652
- Quote: `#клиндамицин** 900 мг`
- Parser: FIXED_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: No temporal marker.

### 6655
- Quote: `#левофлоксацин** 500 мг`
- Parser: FIXED_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: No temporal marker.

### 6654
- Quote: `ципрофлоксацин** 400 мг`
- Parser: FIXED_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: No temporal marker.

### 5961
- Quote: `Цефазолин** 1 г внутривенно медленно`
- Parser: FIXED_PER_DAY  →  AI: REMAINS_AMBIGUOUS
- Evidence: No per-day/dose marker in captured quote.

### 7343
- Quote: `Новорожденные дети: Стартовая доза – 15 мг/кг`
- Parser: AMBIGUOUS  →  AI: REMAINS_AMBIGUOUS
- Evidence: Loading/starting dose framing, no recurring per-day/dose marker.

### 5683
- Quote: `Цефтриаксон**   50-80 мг/кг   4 г    В/в   1-2`
- Parser: AMBIGUOUS  →  AI: TABLE_CONTEXT_REQUIRED
- Evidence: Flattened table row; headers lost, dose/max/route/count concatenated.

### 7895
- Quote: `Цефтриаксон**   50-80 мг/кг   4 г    В/в   1-2`
- Parser: AMBIGUOUS  →  AI: TABLE_CONTEXT_REQUIRED
- Evidence: Flattened table row (dup).

### 6224
- Quote: `детям 2–5 лет в дозе 250 мг (в 2 приема) в течение 5 сут`
- Parser: AMBIGUOUS  →  AI: REMAINS_AMBIGUOUS
- Evidence: "в 2 приема" alone does not establish daily-total vs per-administration.
