# RC-030 Autonomous AI Audit — Table Audit

Table-derived / flattened-table records in the pilot.

## 5683
- Quote: `Цефтриаксон**   50-80 мг/кг   4 г    В/в   1-2`
- AI verdict: TABLE_CONTEXT_REQUIRED
- Table status: OCR_CORRUPTED_EMBEDDED_OK / TABLE_ROW_UNCERTAIN

## 7895
- Quote: `Цефтриаксон**   50-80 мг/кг   4 г    В/в   1-2`
- AI verdict: TABLE_CONTEXT_REQUIRED
- Table status: OCR_CORRUPTED_EMBEDDED_OK / TABLE_ROW_UNCERTAIN

## 5670
- Quote: `Амоксициллин+ клавулановая кислота** внутрь 500/125 мг 3 раза в сутки или 875/125 мг 2 раза в сутки* (дозы указаны для пациентов 12 лет и старше или с массой тела 40 кг и более, см. также инструкцию)`
- AI verdict: CORRECT_FIXED_SINGLE
- Table status: TABLE_TEXT_EXPLICIT (prose sentence recovered by PyMuPDF, not OCR)

## 6072
- Quote: `При высоком риске наличия у пациента штамма пневмококка с повышенной устойчивостью к антибиотикам, рекомендуется использовать повышенные дозировки амоксициллина** (Код АТХ: J01CA04) 80-90 мг/кг/сутки у детей и 1000 мг 3 раза в сутки у взрослых.`
- AI verdict: CORRECT_FIXED_SINGLE
- Table status: TABLE_TEXT_EXPLICIT (prose sentence recovered by PyMuPDF, not OCR)

## 6073
- Quote: `При высоком риске наличия у пациента штамма пневмококка с повышенной устойчивостью к антибиотикам, рекомендуется использовать повышенные дозировки амоксициллина** (Код АТХ: J01CA04) 80-90 мг/кг/сутки у детей и 1000 мг 3 раза в сутки у взрослых.`
- AI verdict: CORRECT_RANGE_DAILY
- Table status: TABLE_TEXT_EXPLICIT (prose sentence recovered by PyMuPDF, not OCR)

## 6074
- Quote: `Однако в большинстве регионов РФ целесообразно назначение амоксициллина** в «стандартной» дозировке: 500- 1000 мг 3 раза в сутки у взрослых и детей с массой более 40 кг и из расчёта 45-60 мг/кг/сутки у детей.`
- AI verdict: CORRECT_RANGE_SINGLE
- Table status: TABLE_TEXT_EXPLICIT (prose sentence recovered by PyMuPDF, not OCR)

## 6075
- Quote: `Однако в большинстве регионов РФ целесообразно назначение амоксициллина** в «стандартной» дозировке: 500- 1000 мг 3 раза в сутки у взрослых и детей с массой более 40 кг и из расчёта 45-60 мг/кг/сутки у детей.`
- AI verdict: CORRECT_RANGE_DAILY
- Table status: TABLE_TEXT_EXPLICIT (prose sentence recovered by PyMuPDF, not OCR)

Cross-reference RC030_TABLE_CLIPPED_TEXT_RECOVERY_REPORT.md: for the Отит/Паратонзиллярный/Лепра pages, layout-bbox + PyMuPDF clipped embedded text recovered 100% correct Cyrillic where MinerU dropped drug names and RapidTable corrupted characters. The two flattened Цефтриаксон rows (5683/7895) are the only genuinely TABLE_CONTEXT_REQUIRED cases in the pilot.
