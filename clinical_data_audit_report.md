# Clinical Data Quality Audit — отчёт

> Read-only. Ничего не изменено. Сгенерировано 2026-07-10T10:22:51Z.
> Источники: raw `antibiotic_regimens` (2675) ↔ `normalized_regimens` (2675) + `clinrecs.abx_drugs` (PDF-скан).
> Атрибуция Extraction/Normalizer — по присутствию поля в сыром извлечении vs нормализованном. Все записи `pending_review`.

## Методологическая оговорка
- **PDF-подтверждено** только для guideline **1638** (сверено с исходной Табл.1 КР).
- Остальные записи — **heuristic_flag** (сигналы из сохранённых данных/цитат), требуют выборочной сверки с PDF.
- Полная построчная сверка КР↔ANTIBIO по каждому из 294 guideline (чтение всех PDF) — рекомендуемый следующий шаг.

## 1. Готовность к Golden Cases
- Всего guideline: **294**
- **Golden-Ready (кандидаты)**: **41** — есть PASS-схема, нет normalizer-флагов, нет extraction-gap.
- Имеют ошибки **Extraction**: **235** guideline
- Имеют ошибки **Normalizer**: **166** guideline
- Имеют пробелы **Dictionary**: **224** guideline
- Кандидаты на **ручную переэкстракцию** (extraction-gap): **83** guideline

## 2. Всего записей в реестре по типам
| Тип | Записей |
|---|---:|
| Extraction | 2236 |
| Dictionary | 1166 |
| Normalizer | 922 |
| DiagnosisIndex | 182 |

По критичности: Critical=0, High=898, Medium=2803, Low=805

## 3. Частота проблем (issue_code)
| issue_code | Тип | Критичность | Кол-во |
|---|---|---|---:|
| `DRUG_UNKNOWN` | Dictionary | Medium | 1166 |
| `ROUTE_NOT_EXTRACTED` | Extraction | Medium | 902 |
| `DOSE_NOT_EXTRACTED` | Extraction | High | 638 |
| `DURATION_NOT_PARSED` | Normalizer | Low | 623 |
| `FREQ_NOT_EXTRACTED` | Extraction | Medium | 613 |
| `DUPLICATE_GUIDELINE_TITLE` | DiagnosisIndex | Low | 182 |
| `DOSE_NOT_PARSED` | Normalizer | High | 116 |
| `FREQ_NOT_PARSED` | Normalizer | Medium | 93 |
| `EXTRACTION_GAP_CANDIDATE` | Extraction | High | 83 |
| `DOSE_DAILY_MISREAD` | Normalizer | High | 61 |
| `DOSE_ALTERNATIVE_COLLAPSED` | Normalizer | Medium | 29 |

## 4. Какие исправления дадут максимальный прирост качества
1. **Расширить словарь (Dictionary)** → снимет `DRUG_UNKNOWN` у **1166** схем (самый массовый, REVIEW→PASS).
2. **Парсер длительности (Normalizer)** → `DURATION_NOT_PARSED` у **623** схем.
3. **Парсер суточной дозы (Normalizer, SAFETY)** → `DOSE_DAILY_MISREAD` у **61** схем — приоритет по безопасности (риск 2× дозы).
4. **Обработка альтернативной дозы 'или'** → `DOSE_ALTERNATIVE_COLLAPSED` у **29** схем.
5. **Переэкстракция многорядных таблиц** → **83** guideline с потерянными схемами (в т.ч. альтернативы при аллергии — High).

## 5. Самое важное (SAFETY-приоритет)
- `DOSE_DAILY_MISREAD` (61) и `DOSE_NOT_PARSED` (116) — прямое влияние на дозу. Разбирать первыми.
- `EXTRACTION_GAP_CANDIDATE` (83) — отсутствие альтернатив (напр. для пациента с аллергией на пенициллины).

## 6. Подтверждённый пример (guideline 1638 — PDF)
- КР «Острый тонзиллит и фарингит» (306_3, «Действует»), Табл.1: первая линия — амоксициллин **1,5 г/сут в 3 приёма или 1,0 г/сут в 2 приёма**, 10 дней.
- ANTIBIO: 1 схема, нормализована в **1,5 г × 2 = 3 г/сут** (Normalizer, High) + потеряно ~13 схем (Extraction, High).
- Решение: Golden Case НЕ создавать; занесено в реестр.

> Полный машиночитаемый реестр — `clinical_data_issues.json` (каждая запись со статусом `pending_review`).
