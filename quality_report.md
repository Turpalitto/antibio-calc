# Quality Audit Report — Medical Normalizer

> Сгенерировано: 2026-07-09 | Medical Normalizer v1.0.0 | Schema v1.0.0

> Источник: knowledge_base.json (294 guidelines, 2675 regimens)


## 1. Общие показатели

| Метрика | Значение |
|---------|----------|
| Всего regimens | 2675 |
| Всего guidelines | 294 |
| Regimens per guideline (avg) | 9.1 |

## 2. Полнота полей (после нормализации)

| Поле | Заполнено | Пропущено | % |
|------|-----------|-----------|---|
| Drug | 2675 | 0 | 100.0% |
| Dose | 1901 | 774 | 71.07% |
| Route | 1740 | 935 | 65.05% |
| Frequency | 1515 | 1160 | 56.64% |
| Duration | 1097 | 1578 | 41.01% |
| Pregnancy | 69 | 2606 | 2.58% |
| Renal adjustment | 75 | 2600 | 2.8% |
| Therapy line | 1608 | 1067 | 60.11% |
| ATC code | 0 | 2675 | 0.0% |

## 3. Полнота raw-полей (до нормализации, из extraction)

| Поле (raw) | Присутствует | Отсутствует | % |
|------------|--------------|-------------|---|
| antibiotic | 2675 | 0 | 100.0% |
| dose | 2037 | 638 | 76.15% |
| unit | 1920 | 755 | 71.78% |
| route | 1773 | 902 | 66.28% |
| frequency | 2062 | 613 | 77.08% |
| duration | 1939 | 736 | 72.49% |
| age_group | 2161 | 514 | 80.79% |
| regimen_type | 2675 | 0 | 100.0% |
| page_number | 2675 | 0 | 100.0% |
| section_name | 2542 | 133 | 95.03% |
| source_quote | 2675 | 0 | 100.0% |
| diagnosis | 2675 | 0 | 100.0% |
| mkb | 2667 | 8 | 99.7% |

## 4. Validation вердикты

| Вердикт | Кол-во | % |
|---------|--------|---|
| PASS | 880 | 32.9% |
| REVIEW | 320 | 12.0% |
| REJECT | 1475 | 55.1% |

## 5. Confidence распределение

| Метрика | Значение |
|---------|----------|
| Min | 0.2 |
| Max | 0.9194 |
| Mean | 0.6312 |
| Median | 0.7044 |
| Std dev | 0.2134 |

| Диапазон | Кол-во | % |
|----------|--------|---|
| 0.0-0.2 | 0 | 0.0% |
| 0.2-0.4 | 553 | 20.7% |
| 0.4-0.6 | 428 | 16.0% |
| 0.6-0.8 | 914 | 34.2% |
| 0.8-1.0 | 780 | 29.2% |

## 6. Validation issues (по коду)

| Код | Кол-во | Severity |
|-----|--------|----------|
| REQUIRED_MISSING | 2869 | ERROR |
| DRUG_UNKNOWN | 1166 | REVIEW |
| ROUTE_UNKNOWN | 935 | REVIEW |
| DOSE_UNIT_UNKNOWN | 23 | REVIEW |
| COMBINATION_MISSING_COMPONENTS | 7 | REVIEW |
| DURATION_OUT_OF_RANGE | 6 | ERROR |
| DOSE_OUT_OF_RANGE | 3 | ERROR |

## 7. Validation issues (по полю)

| Поле | Кол-во issues |
|------|---------------|
| route | 1870 |
| drug | 1166 |
| frequency | 1160 |
| dose | 800 |
| drug_components | 7 |
| duration | 6 |

## 8. Route распределение

| Route | Кол-во |
|-------|--------|
| unknown | 935 |
| iv | 846 |
| oral | 726 |
| im | 59 |
| topical | 53 |
| iv|im | 23 |
| im|iv | 18 |
| oral|iv | 8 |
| iv|oral | 4 |
| ophthalmic | 2 |
| inhalation | 1 |

## 9. Therapy line распределение

| Therapy line | Кол-во |
|--------------|--------|
| unknown | 1067 |
| alternative | 907 |
| first | 701 |

## 10. Population распределение

| Population | Кол-во |
|------------|--------|
| adult | 1805 |
| child | 870 |

## 11. Pregnancy распределение

| Pregnancy | Кол-во |
|-----------|--------|
| None | 2606 |
| True | 69 |

## 12. Performance

| Метрика | Значение |
|---------|----------|
| Total time | 0.304s |
| Regimens/sec | 8800.8 |
| Avg per regimen | 0.114ms |

## 13. Parser errors

| Parser:Error | Кол-во |
|--------------|--------|
| dose:AttributeError | 20 |
| drug:AttributeError | 6 |

**Всего parser errors:** 26 (из 2675 regimens)

## 14. Top missing fields — root cause analysis

### Route (935 missing, 35.0%)

- **Raw presence:** 1773/2675 (66.3%) — 902 regimens без route в extraction

- **Root cause:** LLM extraction (902 absent) + normalizer (33 parse failures)

- **Fix:** Улучшить extraction prompt для route; добавить route synonyms


### Frequency (1160 missing, 43.4%)

- **Raw presence:** 2062/2675 (77.1%) — 613 regimens без frequency в extraction

- **Root cause:** LLM extraction (613 absent) + FrequencyParser не парсит ~547 regimens (77% raw → 56.6% normalized)

- **Fix:** Расширить frequency patterns; улучшить extraction


### Dose (774 missing, 29.0%)

- **Raw presence:** 2037/2675 (76.2%) — 638 regimens без dose в extraction

- **Root cause:** LLM extraction (638 absent) + DoseParser не парсит ~136 regimens (76% raw → 71% normalized) + 20 AttributeError

- **Fix:** Улучшить extraction; fix DoseParser для нестандартных форматов


### Duration (1578 missing, 59.0%)

- **Raw presence:** 1939/2675 (72.5%) — 736 regimens без duration в extraction

- **Root cause:** LLM extraction (736 absent) + DurationParser не парсит ~842 regimens (72% raw → 41% normalized)

- **Fix:** Расширить duration patterns (особенно 'длительно', 'продолжительно'); улучшить extraction


### Drug unknown (1166 REVIEW issues)

- **Root cause:** Dictionary — 441 уникальных неизвестных названий препаратов

- **Categories:** extraction markers (**, #), грамматические падежи, названия групп (фторхинолоны, карбапенемы), комбинации с разным форматированием, опечатки

- **Fix:** Расширить DRUG_SYNONYMS (см. unknown_drugs.csv + dictionary_expansion.md)


### ATC code (2675 missing, 100%)

- **Root cause:** Dictionary — нет mapping drug → ATC code

- **Fix:** Добавить ATC mapping в dictionary (см. dictionary_expansion.md)


### Therapy line (1067 missing, 39.9%)

- **Raw presence:** regimen_type 100% present

- **Root cause:** TherapyLineParser mapping — 1067 'unknown' из 2675 (regimen_type значения не замаплены)

- **Fix:** Расширить _MAPPING в therapy_line_parser.py


### Pregnancy (2606 missing, 97.4%)

- **Root cause:** Missing source data — большинство regimens не упоминают беременность

- **Note:** 69 regimens с pregnancy=True — легитимно, не bug


### Renal adjustment (2600 missing, 97.2%)

- **Root cause:** Missing source data — большинство regimens не упоминают почечную недостаточность

- **Note:** 75 regimens с renal_adjustment=True — легитимно

