# RC-030 Autonomous AI Audit — Defect Clusters

## freq1_shortcut_markerless_mgkg  (4 records — severity HIGH)

- **Regimen IDs**: 6657, 6659, 6658, 6653
- **Source pattern**: bare "N мг/кг" with no /сут or /приём marker; parser assigned WEIGHT_PER_DAY via the frequency==1 algebraic-identity shortcut
- **Parser output**: WEIGHT_PER_DAY
- **AI verdict**: REMAINS_AMBIGUOUS
- **Probable code location**: semantics_parser.py classify_regimen freq==1 shortcut path
- **Deterministic fix possible**: partial — require an explicit textual marker before confirming; freq==1 alone must not classify
- **Corpus rebuild required**: artifact reclassification only (no DB change)

## freq1_shortcut_markerless_fixed  (5 records — severity HIGH)

- **Regimen IDs**: 6651, 6652, 6655, 6654, 5961
- **Source pattern**: bare "N г"/"N мг" fixed dose with no marker (surgical/cesarean prophylaxis lists); parser assigned FIXED_PER_DAY
- **Parser output**: FIXED_PER_DAY
- **AI verdict**: REMAINS_AMBIGUOUS
- **Probable code location**: same freq==1 shortcut path
- **Deterministic fix possible**: partial — same fix as above
- **Corpus rebuild required**: artifact reclassification only

## odnokratno_misclassified  (3 records — severity MEDIUM)

- **Regimen IDs**: 5450, 5895, 5913
- **Source pattern**: "однократно" (explicit one-time) parsed as FIXED_PER_DAY instead of a single-administration type
- **Parser output**: FIXED_PER_DAY
- **AI verdict**: CORRECT_FIXED_SINGLE
- **Probable code location**: semantics_parser.py period/marker detection lacks "однократно"
- **Deterministic fix possible**: yes — add "однократно" as an explicit single-administration marker
- **Corpus rebuild required**: artifact reclassification only

## r_sut_tokenization  (2 records — severity MEDIUM)

- **Regimen IDs**: 6976, 7025
- **Source pattern**: abbreviated "2 р/сут" not recognized as a per-dose+frequency marker (spelled "2 раза в сутки" IS recognized elsewhere)
- **Parser output**: FIXED_PER_DAY
- **AI verdict**: CORRECT_FIXED_SINGLE
- **Probable code location**: semantics_parser.py frequency regex missing the "р/сут" abbreviation
- **Deterministic fix possible**: yes — extend regex to cover "р/сут"/"р/д"
- **Corpus rebuild required**: artifact reclassification only

## dvazhdy_tokenization  (1 records — severity MEDIUM)

- **Regimen IDs**: 7354
- **Source pattern**: "дважды в день" (single-word "twice") not recognized where "2 раза" forms are
- **Parser output**: AMBIGUOUS
- **AI verdict**: CORRECT_FIXED_SINGLE
- **Probable code location**: semantics_parser.py frequency regex missing "дважды"/"трижды"
- **Deterministic fix possible**: yes — add "дважды"/"трижды" word forms
- **Corpus rebuild required**: artifact reclassification only

## weekly_schedule_collapse  (1 records — severity MEDIUM)

- **Regimen IDs**: 5374
- **Source pattern**: "10 мг/кг/сут 1 раз в день – 3 раза в неделю": per-day dose basis explicit, but normalized frequency field=1 loses the 3x/week schedule
- **Parser output**: WEIGHT_PER_DAY
- **AI verdict**: WRONG_FREQUENCY_LINK
- **Probable code location**: medical_normalizer FrequencyParser — weekly periodicity not represented
- **Deterministic fix possible**: partial — needs a schedule-period field, not just frequency/day
- **Corpus rebuild required**: normalizer change + corpus reprocess to populate

## range_not_captured  (9 records — severity HIGH)

- **Regimen IDs**: 6121, 6092, 6579, 7644, 6580, 6073, 6074, 6075, 5534
- **Source pattern**: explicit numeric dose range in source; normalized scalar dose keeps only the lower bound (RC030_RANGE_LOSS_STAGE_RCA)
- **Parser output**: WEIGHT_PER_DAY/FIXED_PER_DOSE (direction correct)
- **AI verdict**: CORRECT_RANGE_DAILY/SINGLE
- **Probable code location**: medical_normalizer/drug_parser.py:139 DoseNormalizer reads match.group(1) only
- **Deterministic fix possible**: yes at normalizer layer — keep group(2); OR additive sandbox re-derivation
- **Corpus rebuild required**: normalizer change + corpus reprocess (or additive sandbox layer)

## table_flattened_headers_lost  (2 records — severity MEDIUM)

- **Regimen IDs**: 5683, 7895
- **Source pattern**: flattened table row "Цефтриаксон 50-80 мг/кг 4 г В/в 1-2" — headers lost, dose/max/route/count concatenated
- **Parser output**: AMBIGUOUS
- **AI verdict**: TABLE_CONTEXT_REQUIRED
- **Probable code location**: upstream extraction table flattening
- **Deterministic fix possible**: no — needs layout-aware table recovery (RC030_TABLE_CLIPPED_TEXT_RECOVERY)
- **Corpus rebuild required**: targeted re-extraction of affected pages

## loading_maintenance_ambiguity  (1 records — severity LOW)

- **Regimen IDs**: 7343
- **Source pattern**: "Стартовая доза – 15 мг/кг" — loading-dose framing without a recurring per-day/dose marker
- **Parser output**: AMBIGUOUS
- **AI verdict**: REMAINS_AMBIGUOUS
- **Probable code location**: n/a — parser correctly ambiguous
- **Deterministic fix possible**: no — genuinely needs table/maintenance-dose context
- **Corpus rebuild required**: targeted re-extraction

## v_n_priema_alone  (1 records — severity LOW)

- **Regimen IDs**: 6224
- **Source pattern**: "250 мг (в 2 приема)" — split-administration count without /сут; daily-total vs per-dose not resolvable
- **Parser output**: AMBIGUOUS
- **AI verdict**: REMAINS_AMBIGUOUS
- **Probable code location**: n/a — parser correctly ambiguous
- **Deterministic fix possible**: no
- **Corpus rebuild required**: none
