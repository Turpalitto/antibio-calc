# Quality Audit — After Parser Improvements

> Полный audit после Tasks 1–4 (FrequencyParser, DurationParser, TherapyLineParser, type guards).
> Сравнение с baseline (до улучшений). Все значения ИЗМЕРЕННЫЕ, не оценочные.
> Дата: 2026-07-09

---

## Executive Summary

Tasks 1–4 завершены (TDD, 803/803 тестов). Parser errors → 0. REJECT 55.1%→44.6%. Confidence 0.6312→0.7188 (+13.9%).

**Parser improvements НЕ полностью исчерпаны** — 118 REJECT ещё parser-flippable, но это hard edge cases (diminishing returns). **Dictionary — следующий high-impact no-LLM рычаг** (438 REVIEW drug-only flippable).

---

## 1. Verdicts — absolute comparison

| Verdict | Baseline | After | Absolute Δ | Relative Δ |
|---------|---------:|------:|-----------:|-----------:|
| PASS | 880 (32.9%) | 1039 (38.8%) | **+159** | +18.1% |
| REVIEW | 320 (12.0%) | 443 (16.6%) | +123 | +38.4% |
| REJECT | 1475 (55.1%) | 1193 (44.6%) | **-282** | -19.1% |
| **Total** | 2675 | 2675 | 0 | — |

**Пояснение:** REVIEW вырос потому что REJECT-регимены с заполненными now required-полями, но DRUG_UNKNOWN, перешли REJECT→REVIEW (drug по-прежнему неизвестен словарём). Это прогресс (REVIEW > REJECT). 159 REJECT→PASS, 123 REJECT→REVIEW.

---

## 2. Field completeness — absolute comparison

| Поле | Baseline missing | After missing | Recovered | Baseline % | After % |
|------|----------------:|--------------:|----------:|-----------:|--------:|
| drug (unknown) | 1166 | 1166 | 0 | 43.59% | 43.59% |
| dose | 774 | 754 | **20** | 28.93% | 28.19% |
| route | 935 | 935 | 0 | 34.95% | 34.95% |
| frequency | 1160 | 706 | **454** | 43.36% | 26.39% |
| duration | 1578 | 951 | **627** | 58.99% | 35.55% |
| pregnancy | 2606 | 2606 | 0 | 97.42% | 97.42% |
| renal_adjustment | 2600 | 2600 | 0 | 97.20% | 97.20% |
| therapy_line | 1067 | 0 | **1067** | 39.89% | 0.00% |
| atc_code | 2675 | 2675 | 0 | 100.00% | 100.00% |
| **Total recovered** | — | — | **2168** | — | — |

---

## 3. Parser errors — absolute

| Метрика | Baseline | After |
|---------|---------:|------:|
| Parser errors | 20 | **0** ✅ |
| % regimens with parser errors | 0.75% | **0.00%** |

---

## 4. Confidence — absolute

| Метрика | Baseline | After | Δ |
|---------|---------:|------:|---:|
| Confidence mean | 0.6312 | 0.7188 | **+0.0876 (+13.9%)** |

---

## 5. Origin classification — absolute comparison

| Источник | Baseline | After | Δ | Baseline % | After % |
|----------|---------:|------:|---:|-----------:|--------:|
| Missing source data | 5206 | 5206 | 0 | 40.4% | 41.9% |
| Dictionary | 3848 | 3842 | -6 | 29.9% | 30.9% |
| LLM extraction | 3055 | 3055 | 0 | 23.7% | 24.6% |
| **Normalization** | **772** | **298** | **-474** | **6.0%** | **2.4%** |
| Validator | 9 | 15 | +6 | 0.1% | 0.1% |

**Ключевое:** Normalization gaps сократились с 772 → 298 (-474, -61%). Это и есть эффект Tasks 1–4. LLM extraction и Missing source не изменились (ожидаемо — без re-extraction).

---

## 6. Recoverability — absolute comparison

| Категория | Baseline | After | Δ |
|-----------|---------:|------:|---:|
| Impossible from existing data | 5206 | 5206 | 0 |
| Recoverable by dictionary | 3848 | 3842 | -6 |
| Requires new LLM extraction | 3055 | 3055 | 0 |
| **Recoverable without LLM** | **781** | **313** | **-468** |

**Ключевое:** Recoverable-without-LLM сократилось с 781 → 313 (-468). Осталось 313 edge cases (93 frequency + 116 dose + 33 route + 215 duration + ... — более сложные паттерны).

---

## 7. REJECT breakdown — per-regimen overlap (absolute)

| Группа | Baseline | After | Δ |
|--------|---------:|------:|---:|
| Parser-only flippable | 403 | 118 | **-285** |
| Partial (norm + llm) | 281 | 111 | -170 |
| LLM-only | 791 | 961 | +170 |
| No required-missing | 0 | 3 | +3 |
| **Total REJECT** | **1475** | **1193** | **-282** |

**Пояснение:** 
- 285 parser-flippable REJECT восстановлены (→ PASS или REVIEW).
- LLM-only вырос 791→961 потому что partial-регимены, у которых norm-часть исправлена, реклассифицированы в LLM-only (осталась только LLM-missing часть).
- 3 REJECT без required-missing — rejected по другим причинам (DURATION_OUT_OF_RANGE/DOSE_OUT_OF_RANGE).

---

## 8. REVIEW breakdown — per-regimen overlap

| Группа | Baseline | After | Δ |
|--------|---------:|------:|---:|
| Drug-only flippable (REVIEW) | 133 | 438 | +305 |
| Other REVIEW | 187 | 5 | -182 |
| **Total REVIEW** | **320** | **443** | +123 |

**Пояснение:** Drug-only REVIEW вырос 133→438 — REJECT-регимены с восстановленными required-полями, но drug по-прежнему неизвестен, перешли REJECT→REVIEW. Все 438 drug-only REVIEW flippable by dictionary expansion.

---

## 9. Per-task measured deltas

| Task | Файл | Новых тестов | Recovered field | ΔPASS | ΔREJECT | ΔREVIEW | ΔConf |
|------|------|------------:|-----------------|------:|--------:|--------:|------:|
| Baseline | — | — | — | 0 | 0 | 0 | 0 |
| 1. FrequencyParser | frequency_parser.py | +42 | freq -454 | +157 | -274 | +117 | +0.0254 |
| 2. DurationParser | duration_parser.py | +19 | dur -627 | 0 | 0 | 0 | +0.0174 |
| 3. TherapyLineParser | therapy_line_parser.py | +7 | tl -1067 | 0 | 0 | 0 | +0.0437 |
| 4. Type guards | drug_parser.py | +9 | dose -20, errors -20 | +2 | -8 | +6 | +0.0011 |
| **Итого** | — | **+77** | **2168 fields** | **+159** | **-282** | **+123** | **+0.0876** |

**Тесты:** 726 → 803 (+77, all pass).

---

## 10. Remaining REJECT analysis

REJECT 1193 разбивка по recoverability:

| Категория | Count | % от REJECT | Что нужно |
|-----------|------:|------------:|-----------|
| LLM-only (raw отсутствует) | 961 | 80.6% | LLM re-extraction (high cost) |
| Partial (norm + llm) | 111 | 9.3% | parser + LLM re-extraction |
| Parser-only flippable | 118 | 9.9% | ещё parser patterns (diminishing returns) |
| No required-missing (validator) | 3 | 0.3% | out-of-range data |
| **Total REJECT** | **1193** | **100%** | — |

**Вывод:** 80.6% оставшегося REJECT требует LLM re-extraction. Parser improvements исчерпаны на ~71% (285/403 parser-flippable восстановлены). Оставшиеся 118 — hard edge cases.

---

## 11. Decision: parser improvements status

**Parser improvements НЕ полностью исчерпаны, но достигли diminishing returns:**
- FrequencyParser: восстановлено 454/547 (83%). Осталось 93 unparsed — сложные составные фразы.
- DurationParser: восстановлено 627/842 (74%). Осталось 215 — составные periop фразы, timing.
- TherapyLineParser: 100% (1067/1067).
- Type guards: 100% (20/20 errors → 0).

**Оставшийся parser potential:** 118 REJECT parser-flippable + часть 111 partial = ~150-200 regimens максимум, при значительных усилиях на edge-case patterns.

**Следующий high-impact no-LLM рычаг: Dictionary expansion.**
- 438 REVIEW drug-only flippable → PASS (при расширении DRUG_SYNONYMS).
- 1166 DRUG_UNKNOWN total → REVIEW 443→~5-50.
- ATC mapping: 0%→~80% (confidence boost, optional field).

---

## 12. Forecast vs actual

| Метрика | RCA прогноз (после tasks 1-6) | Actual (после tasks 1-4) | Разница |
|---------|------------------------------:|------------------------:|--------:|
| REJECT | ~40.1% | **44.6%** | +4.5pp (прогноз включал dictionary+ATC) |
| REVIEW | ~7.0% | **16.6%** | +9.6pp (REJECT→REVIEW shift ещё не обработан dictionary) |
| PASS | ~48.0% | **38.8%** | -9.2pp (REVIEW ещё не flipped в PASS dictionary) |
| Confidence | ~0.72 | **0.7188** | -0.0012 (близко) |

**Пояснение:** Actual после tasks 1-4 (без dictionary/ATC) отличается от прогноза RCA (который включал tasks 1-6). Прогноз REJECT 40% предполагал dictionary expansion — без неё REVIEW остаётся высоким. После dictionary+ATC прогноз должен совпасть.

---

## 13. Methodology

- Источник: `C:\clinrec_downloader\knowledge_base.json` (294 guidelines, 2675 regimens) — НЕ модифицировался.
- Normalizer: `medical_normalizer.normalizer.MedicalNormalizer.normalize` на каждом regimen.
- Baseline snapshot: `rca_snapshot_baseline.json` (до tasks).
- After snapshot: `rca_snapshot_task4_guards.json` (после tasks 1-4).
- Full RCA: `rca_analysis.py` перезапущен после tasks → `rca_results.json` (after state).
- REJECT breakdown: `rca_per_regimen.json` (per-regimen verdict + missing + raw_presence).
- Все изменения — additions only в `frequency_parser.py`, `duration_parser.py`, `therapy_line_parser.py`, `drug_parser.py`. Architecture FROZEN, не рефакторилось.
- Тесты: 726 → 803 (+77 new), все pass, TDD (RED → GREEN для каждой задачи).
- LLM extraction и knowledge_base.json НЕ модифицировались.
