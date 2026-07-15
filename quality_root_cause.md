# Quality Root Cause Analysis

> Анализ причин провалов quality audit на 2675 regimens.
> Сгенерировано из per-regimen нормализации через MedicalNormalizer.
> Цель: определить, где возникают проблемы — LLM extraction / Dictionary / Normalization / Validator / Missing source.

---

## Executive Summary

**Регименов:** 2675  |  **Verdicts:** PASS 880 (32.9%), REVIEW 320 (12.0%), REJECT 1475 (55.1%)
**Parser errors:** 20/2675 (0.7%)

**Главный вывод:** REJECT (55%) управляется REQUIRED_MISSING на dose/route/frequency. Из 2869 required-missing инстансов: **2153 (75%) — LLM extraction gap** (raw поле отсутствует), 716 (25%) — Normalization gap (raw есть, parser не распарсил).

**Dictionary НЕ главный bottleneck.** Dictionary управляет REVIEW (DRUG_UNKNOWN=1166), не REJECT. Расширение словаря снизит REVIEW 12%→~0%, но НЕ снизит REJECT.

---

## Report 1: Per-Field Missing Analysis

Для каждого поля: всего missing, %, затронутые guidelines/diagnoses/PDFs, confidence distribution, top diagnoses/guidelines.

### Сводная таблица

| Поле | Missing | % | Guidelines | Diagnoses | PDFs | Conf mean | Origin (основной) |
|------|--------:|---:|-----------:|----------:|-----:|----------:|-------------------|
| drug (unknown) | 1166 | 43.59% | 224 | 439 | 155 | 0.5273 | Dictionary |
| dose | 774 | 28.93% | 161 | 279 | 113 | 0.3600 | LLM extraction |
| route | 935 | 34.95% | 170 | 331 | 116 | 0.4196 | LLM extraction |
| frequency | 1160 | 43.36% | 200 | 389 | 140 | 0.4548 | LLM extraction |
| duration | 1578 | 58.99% | 220 | 494 | 149 | 0.5664 | Normalization |
| therapy_line | 1067 | 39.89% | 210 | 384 | 147 | 0.5218 | Normalization |
| ATC code | 2675 | 100.00% | 294 | 736 | 193 | 0.6312 | Normalization |
| pregnancy | 2606 | 97.42% | 286 | 714 | 188 | 0.6307 | Missing source data |
| renal_adjustment | 2600 | 97.20% | 288 | 710 | 190 | 0.6324 | Missing source data |

_Всего регименов: 2675_

### Детализация по полям

#### drug (unknown)

- **Missing:** 1166 / 2675 (43.59%)
- **Affected guidelines:** 224  |  **diagnoses:** 439  |  **PDFs:** 155
- **Confidence mean (среди missing):** 0.5273
- **Примечание:** Поле заполнено на 100%, но 1166 препаратов не распознаны словарём (DRUG_UNKNOWN, REVIEW).

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 375 | 299 | 359 | 133 |

**Top-5 diagnoses:**

  - `Врожденная пневмония` — 30
  - `Лепра многобактериального типа` — 24
  - `Лепра малобактериального типа` — 24
  - `Синдром гипоплазии левых отделов сердца` — 21
  - `Туберкулез у детей` — 21

**Top-5 guidelines:**

  - `Лепра [болезнь Гансена]` — 90
  - `Апластическая анемия` — 59
  - `Шигеллез` — 36
  - `Врожденная пневмония` — 30
  - `Туберкулез у детей` — 23

**Top-5 PDFs:**

  - `Лепра [болезнь Гансена].pdf` — 90
  - `Апластическая анемия.pdf` — 59
  - `Шигеллез.pdf` — 36
  - `Врожденная пневмония.pdf` — 30
  - `Туберкулез у детей.pdf` — 23

**Origin:** Dictionary=1166

---

#### dose

- **Missing:** 774 / 2675 (28.93%)
- **Affected guidelines:** 161  |  **diagnoses:** 279  |  **PDFs:** 113
- **Confidence mean (среди missing):** 0.3600
- **Примечание:** Required поле. Отсутствует → REQUIRED_MISSING (ERROR → REJECT).

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 548 | 169 | 57 | 0 |

**Top-5 diagnoses:**

  - `Синдром гипоплазии левых отделов сердца` — 24
  - `Врожденная пневмония` — 24
  - `Туберкулез у детей` — 21
  - `Кампилобактериоз у детей` — 16
  - `Обострение хронического бронхита` — 14

**Top-5 guidelines:**

  - `Апластическая анемия` — 59
  - `Хроническая обструктивная болезнь легких ` — 33
  - `Острые миелоидные лейкозы` — 30
  - `Язвенный колит` — 27
  - `Грипп у взрослых` — 26

**Top-5 PDFs:**

  - `Апластическая анемия.pdf` — 59
  - `Хроническая обструктивная болезнь легких.pdf` — 33
  - `Острые миелоидные лейкозы.pdf` — 30
  - `Язвенный колит.pdf` — 27
  - `Грипп у взрослых.pdf` — 26

**Origin:** LLM extraction=638, Normalization=136

---

#### route

- **Missing:** 935 / 2675 (34.95%)
- **Affected guidelines:** 170  |  **diagnoses:** 331  |  **PDFs:** 116
- **Confidence mean (среди missing):** 0.4196
- **Примечание:** Required поле. route=='unknown' → REQUIRED_MISSING + ROUTE_UNKNOWN.

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 517 | 244 | 174 | 0 |

**Top-5 diagnoses:**

  - `Синдром гипоплазии левых отделов сердца` — 24
  - `Туберкулез у детей` — 21
  - `Язвенная болезнь` — 18
  - `Острая амебная дизентерия` — 18
  - `Кампилобактериоз у детей` — 16

**Top-5 guidelines:**

  - `Лепра [болезнь Гансена]` — 58
  - `Апластическая анемия` — 55
  - `Шигеллез` — 50
  - `Язвенный колит` — 46
  - `Хроническая обструктивная болезнь легких ` — 39

**Top-5 PDFs:**

  - `Лепра [болезнь Гансена].pdf` — 58
  - `Апластическая анемия.pdf` — 55
  - `Шигеллез.pdf` — 50
  - `Язвенный колит.pdf` — 46
  - `Хроническая обструктивная болезнь легких.pdf` — 39

**Origin:** LLM extraction=902, Normalization=33

---

#### frequency

- **Missing:** 1160 / 2675 (43.36%)
- **Affected guidelines:** 200  |  **diagnoses:** 389  |  **PDFs:** 140
- **Confidence mean (среди missing):** 0.4548
- **Примечание:** Required поле. Отсутствует → REQUIRED_MISSING (ERROR → REJECT).

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 534 | 297 | 329 | 0 |

**Top-5 diagnoses:**

  - `Эпиглоттит` — 31
  - `Синдром гипоплазии левых отделов сердца` — 24
  - `Врожденная пневмония` — 23
  - `Гастрит и дуоденит у детей, инфицированные Helicobacter pylori` — 21
  - `Лепра многобактериального типа` — 18

**Top-5 guidelines:**

  - `Лепра [болезнь Гансена]` — 62
  - `Апластическая анемия` — 59
  - `Язвенный колит` — 46
  - `Шигеллез` — 40
  - `Острые миелоидные лейкозы` — 37

**Top-5 PDFs:**

  - `Лепра [болезнь Гансена].pdf` — 62
  - `Апластическая анемия.pdf` — 59
  - `Язвенный колит.pdf` — 46
  - `Шигеллез.pdf` — 40
  - `Острые миелоидные лейкозы.pdf` — 37

**Origin:** Normalization=547, LLM extraction=613

---

#### duration

- **Missing:** 1578 / 2675 (58.99%)
- **Affected guidelines:** 220  |  **diagnoses:** 494  |  **PDFs:** 149
- **Confidence mean (среди missing):** 0.5664
- **Примечание:** Important поле (не required). Отсутствие не вызывает REJECT, но снижает confidence.

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 504 | 209 | 526 | 339 |

**Top-5 diagnoses:**

  - `Врожденная пневмония` — 39
  - `Перелом нижней челюсти` — 30
  - `Повреждение связок коленного сустава; разрыв ПКС` — 26
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых` — 26
  - `Отит средний острый` — 25

**Top-5 guidelines:**

  - `Апластическая анемия` — 59
  - `Переломы бедренной кости (кроме проксимального отдела бедренной кости)` — 53
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых` — 52
  - `Перелом нижней челюсти` — 51
  - `Повреждение связок коленного сустава` — 47

**Top-5 PDFs:**

  - `Апластическая анемия.pdf` — 59
  - `Переломы бедренной кости (кроме проксимального отдела бедренной кости).pdf` — 53
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых.pdf` — 52
  - `Перелом нижней челюсти.pdf` — 51
  - `Повреждение связок коленного сустава.pdf` — 47

**Origin:** LLM extraction=736, Normalization=842

---

#### therapy_line

- **Missing:** 1067 / 2675 (39.89%)
- **Affected guidelines:** 210  |  **diagnoses:** 384  |  **PDFs:** 147
- **Confidence mean (среди missing):** 0.5218
- **Примечание:** Important поле. regimen_type есть в raw у 100%, но TherapyLineParser мапит только 3 значения.

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 336 | 259 | 409 | 63 |

**Top-5 diagnoses:**

  - `Врожденная пневмония` — 29
  - `Перелом нижней челюсти` — 25
  - `Повреждение мениска коленного сустава` — 16
  - `Острые лимфобластные лейкозы` — 15
  - `Кампилобактериоз у детей` — 14

**Top-5 guidelines:**

  - `Перелом нижней челюсти` — 36
  - `Хроническая обструктивная болезнь легких ` — 33
  - `Врожденная пневмония` — 29
  - `Переломы бедренной кости (кроме проксимального отдела бедренной кости)` — 24
  - `Язвенный колит` — 24

**Top-5 PDFs:**

  - `Перелом нижней челюсти.pdf` — 36
  - `Хроническая обструктивная болезнь легких.pdf` — 33
  - `Врожденная пневмония.pdf` — 29
  - `Переломы бедренной кости (кроме проксимального отдела бедренной кости).pdf` — 24
  - `Язвенный колит.pdf` — 24

**Origin:** Normalization=1067

---

#### ATC code

- **Missing:** 2675 / 2675 (100.00%)
- **Affected guidelines:** 294  |  **diagnoses:** 736  |  **PDFs:** 193
- **Confidence mean (среди missing):** 0.6312
- **Примечание:** Optional поле. 0% coverage — нет drug→ATC mapping. Не влияет на verdict.

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 553 | 428 | 914 | 780 |

**Top-5 diagnoses:**

  - `Врожденная пневмония` — 58
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых` — 36
  - `Брюшной тиф` — 32
  - `Повреждение связок коленного сустава; разрыв ПКС` — 32
  - `Эпиглоттит` — 31

**Top-5 guidelines:**

  - `Лепра [болезнь Гансена]` — 114
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых` — 71
  - `Шигеллез` — 70
  - `Хронический синусит` — 65
  - `Апластическая анемия` — 59

**Top-5 PDFs:**

  - `Лепра [болезнь Гансена].pdf` — 114
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых.pdf` — 71
  - `Шигеллез.pdf` — 70
  - `Хронический синусит.pdf` — 65
  - `Апластическая анемия.pdf` — 59

**Origin:** Normalization=2675

---

#### pregnancy

- **Missing:** 2606 / 2675 (97.42%)
- **Affected guidelines:** 286  |  **diagnoses:** 714  |  **PDFs:** 188
- **Confidence mean (среди missing):** 0.6307
- **Примечание:** Optional поле. 97.4% легитимно отсутствует (неактуально для большинства regimens).

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 533 | 427 | 896 | 750 |

**Top-5 diagnoses:**

  - `Врожденная пневмония` — 58
  - `Повреждение связок коленного сустава; разрыв ПКС` — 32
  - `Эпиглоттит` — 31
  - `Перелом нижней челюсти` — 30
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых` — 30

**Top-5 guidelines:**

  - `Лепра [болезнь Гансена]` — 114
  - `Шигеллез` — 70
  - `Хронический синусит` — 65
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых` — 59
  - `Апластическая анемия` — 59

**Top-5 PDFs:**

  - `Лепра [болезнь Гансена].pdf` — 114
  - `Шигеллез.pdf` — 70
  - `Хронический синусит.pdf` — 65
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых.pdf` — 59
  - `Апластическая анемия.pdf` — 59

**Origin:** Missing source data=2606

---

#### renal_adjustment

- **Missing:** 2600 / 2675 (97.20%)
- **Affected guidelines:** 288  |  **diagnoses:** 710  |  **PDFs:** 190
- **Confidence mean (среди missing):** 0.6324
- **Примечание:** Optional поле. 97.2% легитимно отсутствует.

**Confidence distribution (среди missing):**

| 0.0–0.2 | 0.2–0.4 | 0.4–0.6 | 0.6–0.8 | 0.8–1.0 |
|---:|---:|---:|---:|---:|
| 0 | 526 | 427 | 887 | 760 |

**Top-5 diagnoses:**

  - `Врожденная пневмония` — 58
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых` — 36
  - `Брюшной тиф` — 32
  - `Перелом нижней челюсти` — 30
  - `Лепра многобактериального типа` — 30

**Top-5 guidelines:**

  - `Лепра [болезнь Гансена]` — 114
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых` — 71
  - `Шигеллез` — 70
  - `Хронический синусит` — 61
  - `Врожденная пневмония` — 58

**Top-5 PDFs:**

  - `Лепра [болезнь Гансена].pdf` — 114
  - `Брюшной тиф (инфекция, вызванная Salmonella Typhi) у взрослых.pdf` — 71
  - `Шигеллез.pdf` — 70
  - `Хронический синусит.pdf` — 61
  - `Врожденная пневмония.pdf` — 58

**Origin:** Missing source data=2600

---

## Report 2: Issue Origin Classification

Каждая проблема классифицирована по источнику возникновения.

**Категории:**
- **LLM extraction** — raw поле отсутствует (LLM не извлёк из PDF)
- **Dictionary** — drug неизвестен словарю (DRUG_UNKNOWN) или нет ATC mapping
- **Normalization** — raw поле есть, но parser не смог нормализовать (pattern gap)
- **Validator** — данные есть, но out-of-range (DURATION_OUT_OF_RANGE, DOSE_OUT_OF_RANGE)
- **Missing source data** — поле легитимно отсутствует (pregnancy, renal для большинства)
- **Unknown** — не классифицировано

### Overall origin (все missing/issue инстансы)

| Категория | Count | % |
|-----------|------:|---:|
| Missing source data | 5206 | 40.4% |
| Dictionary | 3848 | 29.9% |
| LLM extraction | 3055 | 23.7% |
| Normalization | 772 | 6.0% |
| Validator | 9 | 0.1% |
| **Всего** | **12890** | **100%** |

> **Важно:** общий счёт включает optional поля (pregnancy/renal/ATC), которые легитимно отсутствуют и не влияют на verdict. Для оценки REJECT нужно изолировать required fields.

### Origin REQUIRED_MISSING (драйвер REJECT, только required fields)

Required fields: dose, route, frequency (drug всегда заполнен). Всего REQUIRED_MISSING инстансов: **2869** (на 1475 REJECT регименов, ≈1.95 на regimen).

| Поле | Missing | LLM extraction | Normalization | % LLM | % Norm |
|------|--------:|---------------:|--------------:|------:|-------:|
| dose | 774 | 638 | 136 | 82% | 18% |
| route | 935 | 902 | 33 | 96% | 4% |
| frequency | 1160 | 613 | 547 | 53% | 47% |
| **Итого** | **2869** | **2153** | **716** | **75%** | **25%** |

**Вывод:** 75% REJECT-причин — LLM не извлёк поле (raw отсутствует). 25% — parser не смог распарсить присутствующий raw. Dictionary здесь ни при чём.

### Origin REVIEW (драйвер REVIEW)

REVIEW управляется **DRUG_UNKNOWN = 1166** (Dictionary gap). Сейчас REVIEW regimens = 320. Расширение DRUG_SYNONYMS — единственный способ снизить REVIEW.

### Origin per-field (детально)

| Поле | LLM | Dictionary | Normalization | Validator | Missing source | Unknown |
|------|----:|-----------:|--------------:|----------:|---------------:|--------:|
| drug (unknown) | 0 | 1166 | 0 | 0 | 0 | 0 |
| dose | 638 | 0 | 136 | 0 | 0 | 0 |
| route | 902 | 0 | 33 | 0 | 0 | 0 |
| frequency | 613 | 0 | 547 | 0 | 0 | 0 |
| duration | 736 | 0 | 842 | 0 | 0 | 0 |
| therapy_line | 0 | 0 | 1067 | 0 | 0 | 0 |
| ATC code | 0 | 0 | 2675 | 0 | 0 | 0 |
| pregnancy | 0 | 0 | 0 | 0 | 2606 | 0 |
| renal_adjustment | 0 | 0 | 0 | 0 | 2600 | 0 |

---

## Report 3: Recoverability Classification

Каждый missing инстанс классифицирован по возможности восстановления.

**Категории:**
- **Recoverable without LLM** — raw поле есть, нужен только лучший parser (low cost)
- **Recoverable by dictionary** — drug неизвестен / нет ATC, нужно расширение словаря (low cost)
- **Requires new LLM extraction** — raw поле отсутствует, нужен re-extract (high cost)
- **Impossible from existing data** — поле легитимно отсутствует (pregnancy, renal)

### Overall recoverability (все missing инстансы)

| Категория | Count | % |
|-----------|------:|---:|
| Impossible from existing data | 5206 | 40.4% |
| Recoverable by dictionary | 3848 | 29.9% |
| Requires new LLM extraction | 3055 | 23.7% |
| Recoverable without LLM | 781 | 6.1% |
| **Всего** | **12890** | **100%** |

### Recoverability REQUIRED_MISSING (REJECT driver)

| Категория | Count | % | Влияние на verdict |
|-----------|------:|---:|--------------------|
| Recoverable without LLM (parser fix) | 716 | 25% | Снизит REJECT |
| Requires new LLM extraction | 2153 | 75% | Снизит REJECT (после re-extract) |
| **Итого required-missing** | **2869** | **100%** | |

### Recoverability REVIEW (DRUG_UNKNOWN)

| Категория | Count | Влияние |
|-----------|------:|---------|
| Recoverable by dictionary | 1166 | Снизит REVIEW 320→~0 |

### Recoverability per-field (детально)

| Поле | Recoverable without LLM | Recoverable by dictionary | Requires new LLM | Impossible |
|------|------------------------:|--------------------------:|-----------------:|-----------:|
| drug (unknown) | 0 | 1166 | 0 | 0 |
| dose | 136 | 0 | 638 | 0 |
| route | 33 | 0 | 902 | 0 |
| frequency | 547 | 0 | 613 | 0 |
| duration | 842 | 0 | 736 | 0 |
| therapy_line | 1067 | 0 | 0 | 0 |
| ATC code | 0 | 2675 | 0 | 0 |
| pregnancy | 0 | 0 | 0 | 2606 |
| renal_adjustment | 0 | 0 | 0 | 2600 |

---

## Conclusion & Recommended Priority

### Что НЕ главный bottleneck

- **Dictionary** — управляет REVIEW (1166 DRUG_UNKNOWN), не REJECT. REJECT=55% — главная проблема. Dictionary expansion не снизит REJECT.
- **Validator** — 9 out-of-range issues (0.1%). Незначительно.
- **Missing source data** — pregnancy/renal легитимно отсутствуют (97%+). Не проблема.

### Главный bottleneck: LLM extraction

- **2153 required-missing инстансов (75% от REQUIRED_MISSING)** — LLM не извлёк dose/route/frequency из PDF.
- Это драйвер 1475 REJECT регименов (55% всего аудита).
- Без re-extraction REJECT нельзя снизить существенно.

### Вторичный bottleneck: Normalization (parser gaps)

- **716 required-missing инстансов (25% от REQUIRED_MISSING)** — raw есть, parser не справился.
- FrequencyParser: 547 (главный normalization gap среди required).
- Дополнительно: duration 842 (important), therapy_line 1067 (important) — не REJECT, но снижают confidence.

### Рекомендация: порядок задач по impact / cost

| # | Задача | Cost | Impact на verdict | Impact на confidence |
|---|--------|------|-------------------|----------------------|
| 1 | **FrequencyParser expansion** (~5 patterns) | Low | REJECT ↓ (547 freq-missing recoverable) | + |
| 2 | **DRUG_SYNONYMS expansion** (~60 synonyms) | Low | REVIEW 320→~0 (12%→~0%) | + |
| 3 | **TherapyLineParser expansion** (~8 mappings) | Low | — (important field) | confidence ↑ 1067 regimens |
| 4 | **DurationParser expansion** (~patterns) | Low-Med | — (important field) | confidence ↑ 842 regimens |
| 5 | **RouteParser / DoseParser type guards** (26 errors) | Low | parser errors 20→0 | + |
| 6 | **DRUG_ATC mapping** (~75 drugs) | Low | — (optional) | ATC 0%→~80% |
| 7 | **LLM re-extraction** (improve prompt, re-run) | **High** | **REJECT ↓↓ (2153 required-missing)** | +++ |

### Итог

**Dictionary expansion НЕ первый приоритет.** Это task #2 — снижает REVIEW, не REJECT.

**Первый приоритет — FrequencyParser expansion** (low cost, 547 required-missing recoverable, прямой REJECT↓).

**Крупнейший эффект — LLM re-extraction** (task #7, high cost), но это отдельный проект: переписать prompt, re-run 294 PDF, пересобрать KB, re-normalize. Без него REJECT не опустится ниже ~40%.

### Точный прогноз (per-regimen overlap анализ)

REJECT 1475 разбит на 3 группы по recoverability required-missing полей:

| Группа | Regimens | Описание | Что нужно |
|--------|---------:|----------|-----------|
| Parser-only flippable | 403 | все req-missing имеют raw (нужен только parser fix) | FrequencyParser + Route/Dose patterns |
| Partial | 281 | часть req-missing raw есть, часть отсутствует | parser fix + LLM re-extract |
| LLM-only | 791 | все req-missing raw отсутствуют | только LLM re-extraction |

**Прогноз после tasks 1–6 (parser + dictionary, без LLM re-extraction):**

| Метрика | Сейчас | После | Примечание |
|---------|--------|-------|------------|
| REJECT | 1475 (55.1%) | ~1072 (40.1%) | -403 (parser-only flippable) |
| REVIEW | 320 (12.0%) | ~187 (7.0%) | -133 (drug-only REVIEW) |
| PASS | 880 (32.9%) | ~1283 (48.0%) | +403 |
| ATC | 0% | ~80% | DRUG_ATC mapping |
| Confidence | 0.63 | ~0.72 | duration + therapy_line + ATC |

**Для REJECT 55%→25% (цель) — необходим LLM re-extraction (task 7).** 
Parser + dictionary дают REJECT 55%→40%. Оставшиеся 40% (1072 regimens: 791 LLM-only + 281 partial) требуют re-extraction.

---

## Methodology

- Источник: `C:\clinrec_downloader\knowledge_base.json` (294 guidelines, 2675 regimens)
- Normalizer: `medical_normalizer.normalizer.MedicalNormalizer.normalize` на каждом regimen
- Per-regimen capture: verdict, confidence, missing fields (normalized), raw field presence, issue codes/fields
- Missing definition: normalized field empty/None/unknown (drug: DRUG_UNKNOWN из validator)
- Origin: raw поле отсутствует → LLM extraction; raw есть, normalized missing → Normalization (drug → Dictionary); drug_unknown / ATC → Dictionary; pregnancy/renal → Missing source; out-of-range → Validator
- Recoverability: raw есть + parser gap → Recoverable without LLM; drug/ATC → by dictionary; raw отсутствует → Requires new LLM; pregnancy/renal → Impossible
- Required fields: drug, dose, route, frequency (per `confidence.py`); important: duration, population, therapy_line; optional: atc_code, pregnancy, renal_adjustment
- REQUIRED_MISSING = 2869 = dose(774)+route(935)+frequency(1160) — точное совпадение с validator issue_codes
