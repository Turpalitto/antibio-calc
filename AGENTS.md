# AGENTS.md — ANTIBIO Project Overview

> Current authority (2026-07-15): `GOVERNANCE_SOURCE_OF_TRUTH.md`. P5.6 is ACCEPTANCE/NOT COMPLETE; P6 BLOCKED. Never connect Clinical Engine, auto-approve medicine, commit production DB/PDF, or restore plaintext credentials. Historical instructions below apply only when non-conflicting.

> Single source of truth for AI agents working on ANTIBIO.
> Last updated: 2026-07-10 | Phase: Clinical Decision Engine — verification & production hardening

---

## 0. ⚠️ ОБЯЗАТЕЛЬНЫЙ ПРОТОКОЛ ХЕНДОФФА (для ЛЮБОЙ IDE / AI-агента)

**Это правило действует для любого агента и любой IDE (Claude Code, Cursor, Copilot, Windsurf, Codex, и т.д.). Соблюдай его без исключений.**

Проект ведётся так, чтобы работу можно было продолжить из **любой** IDE без потери контекста. Вся память проекта живёт в Markdown-файлах в корне репозитория. Поэтому:

**В конце КАЖДОЙ задачи (не только крупного milestone) ты ОБЯЗАН обновить MD-файлы:**

| Файл | Что записать |
|------|--------------|
| `AI_LOG.md` | Новая запись сверху: дата, что сделал, какие файлы изменил/создал, ключевые решения, результат тестов. Хронологический лог. |
| `PROJECT_STATE.md` | Текущее состояние: версия, статус фазы, что готово / что нет, результат последнего прогона тестов. |
| `NEXT_TASK.md` | Что делать следующим: конкретные шаги, блокеры, открытые решения. Так следующий агент знает, с чего начать. |
| `DECISIONS.md` | Любое нетривиальное решение (архитектурное, по данным, отклонение от спеки) — датированная запись с обоснованием. |

**Правила записи (чтобы любая IDE могла продолжить):**
1. **Никогда не полагайся на память чата или контекст сессии** — только на MD-файлы. Считай, что следующий агент стартует с нуля и прочитает только эти файлы.
2. **Пиши абсолютные факты:** пути к файлам, имена функций/классов, точные команды запуска тестов, номера версий. Не «поправил парсер», а «`clinical_engine/stages/dose_adjustment.py`: убрал dead-код `excluded_here`».
3. **Конвертируй относительные даты в абсолютные** («сегодня» → `2026-07-10`).
4. **Всегда указывай, как проверить:** команда прогона тестов + актуальный результат (`pytest medical_normalizer/tests/ clinical_engine/tests/ -q` → 1049 passed).
5. **Держи тесты зелёными** и фиксируй это в записи.
6. **Порядок чтения при онбординге:** Start with HANDOFF.md (central index + required reading list). Then follow references. Onboarding complete only after explicitly reporting the 6 items (Frozen Components, Current Milestone, Active Issue, Workflow Stage, Current Test Status, Next Implementation Step). If unclear, stop and ask. Do not code until approved.

**Этот протокол самоподдерживающийся:** он записан здесь именно для того, чтобы любая новая IDE, прочитав `AGENTS.md`, продолжила вести MD-файлы точно так же.

## Clinical Traceability Rule (permanent law)

Every physician-visible recommendation must be traceable.

For every recommendation the system must always be able to answer:

1. Which guideline(s) produced it?
2. Which regimen(s) were considered?
3. Which safety filters modified it?
4. Which terminology mapping affected it?
5. Which engine stages participated?
6. Why alternatives were rejected?
7. Which evidence supports the final recommendation?

No recommendation may become a black box.

This is the law. All P1+ work must preserve and expose this chain. Physician must see the full causal path, not "ИИ так решил."

## Optimization Rule (permanent)

Never optimize infrastructure unless it directly improves clinical decision quality, safety, maintainability, or measurable performance.

If no measurable benefit exists, do not change it.

---

## 0.1 РОЛЬ АГЕНТА — SUPERSEDED (см. ANTIBIO_PROJECT_CONSTITUTION.md)

> ⚠️ **Эта секция устарела и оставлена как исторический артефакт.** С 2026-07-14 действующая
> роль агента определяется в `ANTIBIO_PROJECT_CONSTITUTION.md` §2.1 (Production Architecture Lead
> + Senior Implementation Engineer + Medical Software QA + Production Auditor). Текст ниже
> описывает роль, действовавшую с 2026-07-10 по 2026-07-14 (Reviewer-only), и приводится только
> для истории. **Всегда сверяйся с `ANTIBIO_PROJECT_CONSTITUTION.md`, а не с этим блоком.**

**(Историческое, 2026-07-10 — 2026-07-14):** Роль агента в проекте была **не разработчик новых функций**, а Technical Reviewer и Medical QA Engineer.

**Нельзя:** предлагать новые модули без явной просьбы; менять архитектуру; переписывать код «ради красоты»; рефакторить без явной пользы; начинать новые milestone самому; придумывать функции; усложнять проект. Любое изменение обосновывается **измерением или медицинской необходимостью**.

**Обязанности (по конкретной задаче):** анализ Golden Clinical Cases; поиск регрессий; поиск медицинских ошибок; проверка соответствия клиническим рекомендациям (КР); помощь с врачебной валидацией, документацией, production-релизами.

Process frozen. Focus clinical product. Traceability law. No new rules.

**Golden Case** → проверить вывод Engine, сравнить с ожидаемым; при отличии — объяснить причину (ошибка движка / данных / кейса / неоднозначность КР). **Не исправлять автоматически.**
**Клиническая рекомендация** → найти guideline, показать различия с базой, предложить (не применять) изменения.
**Новая версия КР** → найти изменения, затронутые диагнозы, различия, подготовить (не применить) обновление базы.

**Ждать конкретной задачи. Автоматически ничего не менять в коде/данных.**

Onboard via HANDOFF.md. Report 6 items to confirm. Clinical value + Traceability + Optimization rules are law. No new process rules.

---

## 1. Project Purpose

ANTIBIO — система для создания и использования базы знаний по антибиотикотерапии из клинических рекомендаций (КР) Минздрава РФ.

**Два продукта:**
1. **antibio-calc** — веб-калькулятор доз антибиотиков для врачей (single-page HTML)
2. **Pipeline + Medical Normalizer** — извлечение и нормализация данных из 2000+ PDF КР

**Цель:** предоставить врачу структурированные, нормализованные, валидированные схемы антибиотикотерапии из доказательной базы Минздрава РФ.

---

## 2. Architecture

```
PDF (2000+) → Downloader → Classifier → LLM Extraction → knowledge_base.json
                                                              ↓
                                                    MedicalNormalizer
                                                              ↓
                                                    NormalizerDB (SQLite)
                                                              ↓
                                                    antibio-calc (HTML)
```

**Architecture: FROZEN.** Не подлежит рефакторингу.

**P4 — Document Intelligence Platform ✅ COMPLETE + Production Ready**

Pipeline:
Digital PDF
↓
Multi-Engine (PyMuPDF primary + fallbacks)
↓
Layout
↓
Semantic Layer (entities + norm + kobj + consistency)
↓
Versioned Knowledge Base (P4.4 COMPLETE)
↓
Clinical Engine

**Agents:** After P4 all knowledge work goes through Versioned KB. No direct PDF or raw semantic objects to engine.

P4 closed. Next: P4.4 (immutable objects, versioning, dedup, review). No auto KG. Follow P4/P5/P6/P7. Paired validation.

Current: PyMuPDF + MinerU (per-page, cache, metrics, provenance v1) live. Docling added as third engine (normalization). Future: layout (DocLayout-YOLO), advanced tables.

See extraction/ for implementation (DO NOT bypass).

---

## 3. Current Phase

**Clinical Capability (P1+)**

Process building complete. No new rules.

Focus: clinical value for physician, real scenarios, Golden Cases, implementation of P1 Terminology etc.

P0 infrastructure frozen. Traceability law active.

No process improvement. Product and clinical quality.

**Architecture завершена:**
- ✅ PDF downloader
- ✅ PDF analyzer
- ✅ Antibiotic classifier
- ✅ LLM extraction
- ✅ Knowledge Base generated
- ✅ Medical Normalizer (13 модулей, 823 тестов)
- ✅ SQLite persistence
- ✅ Quality Audit (2675 regimens)
- ✅ Root Cause Analysis (per-regimen origin + recoverability)
- ✅ Medical Dictionary subsystem (terminology DB extracted from Python, 10 JSON, loader, 441 candidates pending review)

---

## 4. Completed Milestones

| Milestone | Date | Result |
|-----------|------|--------|
| PDF downloader | 2026-07-07 | 963 PDF скачано |
| Classifier (A/B/C/D) | 2026-07-08 | 2000 PDF за 0.17с |
| LLM extraction (DeepSeek) | 2026-07-09 | 294 guidelines, 2675 regimens |
| Knowledge Base | 2026-07-09 | knowledge_base.json + metadata.sqlite |
| Medical Normalizer | 2026-07-09 | 13 модулей, 726 тестов, 99.9% coverage |
| Quality Audit | 2026-07-09 | PASS 33%, REVIEW 12%, REJECT 55% |
| Root Cause Analysis | 2026-07-09 | REJECT 75% LLM / 25% Normalization; dictionary не главный |
| Parser Improvements (Tasks 1-4) | 2026-07-09 | REJECT 55%→44.6%, parser errors 20→0, conf +13.9% |
| Medical Dictionary subsystem | 2026-07-09 | terminology DB extracted from Python, 10 JSON, loader, 441 candidates pending review |
| antibio-calc | 2026-07-08 | 72 нозологии, 40 препаратов |

---

## 5. Current Statistics

### Pipeline
| Metric | Value |
|--------|-------|
| Total PDFs | 963 |
| Guidelines with antibiotics | 294 |
| Extracted regimens | 2675 |
| LLM provider | DeepSeek V4 Flash (opencode.ai/zen) |

### Medical Normalizer
| Metric | Value |
|--------|-------|
| Modules | 13 |
| Tests | 726/726 (100%) |
| Coverage | 99.9% |
| Performance | 8800 regimens/s |
| Confidence mean | 0.6312 |

### Quality Audit (2675 regimens)
| Verdict | Count | % |
|---------|-------|---|
| PASS | 880 | 32.9% |
| REVIEW | 320 | 12.0% |
| REJECT | 1475 | 55.1% |

### Field Completeness
| Field | % |
|-------|---|
| Drug | 100% |
| Dose | 71.1% |
| Route | 65.1% |
| Frequency | 56.6% |
| Duration | 41.0% |
| Therapy line | 60.1% |
| ATC code | 0% |
| Pregnancy | 2.6% |
| Renal adjustment | 2.8% |

---

## 6. Directory Structure

```
C:\ANTIBIO/
├── medical_dictionary/            # Medical Dictionary subsystem (terminology DB, source of truth)
│   ├── __init__.py                # package + rules
│   ├── loader.py                  # cached JSON loaders (lru_cache), reload_all()
│   ├── drug_synonyms.json         # synonym→canonical (152 entries)
│   ├── drug_atc.json              # canonical→ATC (0, pending review)
│   ├── drug_groups.json           # group→ATC prefix (0, pending review)
│   ├── route_dictionary.json      # route synonyms (41)
│   ├── unit_dictionary.json       # unit normalization (28)
│   ├── frequency_dictionary.json  # pattern descriptors (reference)
│   ├── duration_dictionary.json   # pattern descriptors (reference)
│   ├── pregnancy_dictionary.json  # keyword patterns (reference)
│   ├── renal_dictionary.json      # keyword patterns (reference)
│   ├── metadata.json              # version, inventory, counts
│   ├── unknown_drugs.csv          # 441 unknown drugs ranked by occurrence
│   └── dictionary_candidates.json # 441 candidates, all pending_review
├── medical_normalizer/          # Medical Normalizer (FROZEN)
│   ├── models.py                # NormalizedRegimen, ParserResult, ConfidenceScore
│   ├── dictionary.py            # data-loading layer (loads medical_dictionary/*.json via loader)
│   ├── drug_parser.py           # DrugParser, DoseNormalizer
│   ├── route_parser.py          # RouteParser
│   ├── frequency_parser.py      # FrequencyParser
│   ├── duration_parser.py       # DurationParser
│   ├── population_parser.py     # AgeParser, PregnancyParser, GFRParser
│   ├── therapy_line_parser.py   # TherapyLineParser
│   ├── confidence.py            # ConfidenceCalculator (weighted, 100% coverage)
│   ├── validator.py             # Validator (PASS/REVIEW/REJECT, 100% coverage)
│   ├── normalizer.py            # MedicalNormalizer (single entry point, 100% coverage)
│   ├── db.py                    # NormalizerDB (SQLite UPSERT, 99% coverage)
│   └── tests/                   # 823 тестов
├── src/pipeline/                # Pipeline (извлечение КР)
│   ├── main.py, config.py, database.py, prefilter.py
│   ├── extractor_llm.py, section_detector.py, progress.py
│   └── *_llm.py, *_extractor.py
├── src/llm/                     # LLM провайдеры
│   ├── llm_provider.py
│   └── providers/deepseek.py
├── src/tests/                   # Pipeline тесты (39 тестов)
├── db/                          # Данные калькулятора
│   ├── index.json, schema.json
│   ├── build_db.ps1
│   ├── antibio_db.json
│   └── diseases/*.json
├── antibiotic_calc.html         # Готовое приложение (НЕ РЕДАКТИРОВАТЬ ВРУЧНУЮ)
├── antibiotic_calc.html.template # Шаблон (редактировать здесь)
├── build_html.ps1               # Сборка: template + DB → HTML
├── server.js                    # Локальный сервер (http://0.0.0.0:8080)
├── prefilter_rules.json         # Бизнес-правила prefilter
├── quality_report.md            # Quality Audit отчёт
├── quality_root_cause.md        # Root Cause Analysis (origin + recoverability)
├── quality_audit_after_parsers.md # Quality Audit after Tasks 1-4 (measured comparison)
├── field_statistics.csv         # Статистика по полям
├── unknown_drugs.csv            # 441 неизвестный препарат
├── dictionary_expansion.md      # Рекомендации (~160 записей)
├── production_readiness.md      # Оценка готовности
├── quality_audit_data.json      # Raw JSON статистика
├── PROJECT_STATE.md             # Состояние проекта
├── AI_LOG.md                    # Лог работы AI
├── NEXT_TASK.md                 # Следующие задачи
├── DECISIONS.md                 # Архитектурные решения
├── README.md                    # Project README
└── AGENTS.md                    # Этот файл
```

**Данные (вне репозитория):**
```
C:\clinrec_downloader/
├── downloads_active/            # 477 PDF для LLM-экстракции
├── archive_review/              # 361 PDF требующие просмотра
├── archive_no_antibiotics/      # 123 PDF без антибиотиков
├── quarantine/                  # 2 orphan PDF
├── knowledge_base.json          # 294 guidelines, 2675 regimens
├── extraction_raw.json          # Raw extraction
├── extraction_validated.json    # Validated (mock)
├── extraction_progress.json     # Progress tracking
└── metadata.sqlite              # Pipeline metadata
```

---

## 7. Medical Pipeline

```
1. Downloader (clinrec_downloader)
   API Минздрава → PDF (963 unique)

2. Classifier (src/pipeline/prefilter.py)
   PDF → A (need LLM) / B (review) / C (no antibiotics) / D (skip)
   931 active / 298 no_abx / 771 review

3. LLM Extraction (src/pipeline/extractor_llm.py)
   PDF → raw regimens (JSON)
   DeepSeek V4 Flash, 294 guidelines, 2675 regimens

4. Validation (src/pipeline/main.py cmd_validate)
   Mock validation (confidence 1.0) — 164 IDs
   Real validation pending — 130 IDs

5. Knowledge Base (src/pipeline/database.py)
   → knowledge_base.json + metadata.sqlite
   294 guidelines, 2675 regimens
```

---

## 8. Normalization Pipeline

```
MedicalNormalizer.normalize(raw_dict)
    │
    ├── DrugParser          → drug_normalized, drug_components, atc_code
    ├── DoseNormalizer      → dose_value, dose_unit
    ├── RouteParser         → route (oral/iv/im/topical/...)
    ├── FrequencyParser     → frequency_per_day
    ├── DurationParser      → duration_days_min/max/recommended
    ├── PopulationParser    → adult, child, pregnancy, renal_adjustment
    │   ├── AgeParser
    │   ├── PregnancyParser
    │   └── GFRParser
    ├── TherapyLineParser   → therapy_line (first/alternative/reserve)
    │
    ├── ConfidenceCalculator → ConfidenceResult (weighted: required=3, important=2, optional=1)
    │
    ├── Validator           → ValidationReport (PASS/REVIEW/REJECT)
    │   ├── required fields check
    │   ├── drug exists check
    │   ├── dose > 0 check
    │   ├── frequency valid check
    │   ├── duration valid check
    │   ├── route valid check
    │   ├── component consistency check
    │   ├── ATC format check
    │   ├── pregnancy consistency check
    │   └── renal adjustment consistency check
    │
    └── NormalizedResult (immutable)
        ├── regimen: NormalizedRegimen
        ├── confidence: ConfidenceResult
        ├── validation: ValidationReport
        ├── warnings: tuple[str, ...]
        ├── errors: tuple[ParserError, ...]
        ├── execution_metadata
        ├── normalizer_version
        ├── parser_execution_order
        └── processing_time
```

---

## 9. SQLite Schema

**Table: `normalized_regimens`** (42 columns)

| Column group | Columns |
|--------------|---------|
| PK | regimen_id, guideline_id |
| Drug | drug_original, drug_normalized, drug_components (JSON), atc_code |
| Dose | dose (REAL), dose_unit |
| Route | route |
| Frequency | frequency (REAL) |
| Duration | duration_min, duration_max, duration_recommended (REAL) |
| Therapy | therapy_line |
| Population | population, adult, child, pregnancy, renal_adjustment (INTEGER) |
| Confidence | overall_confidence, field_confidence (JSON), parser_confidence |
| Validation | validation_verdict, validation_issues (JSON), validation_errors, validation_reviews, validation_warnings |
| Source | source_pdf, source_page, source_quote, diagnosis, mkb |
| Versioning | normalizer_version, schema_version |
| Manual (preserved on UPSERT) | review_status, reviewed_by, review_date, manual_notes, manual_override, approved |
| Timestamps | created_at (preserved), updated_at (updated) |

**UPSERT:** `INSERT ... ON CONFLICT(guideline_id, regimen_id) DO UPDATE SET [normalized columns only]`
- Manual fields НЕ перезаписываются при re-normalization
- created_at сохраняется
- updated_at обновляется

**Indexes (11):**
idx_guideline_id, idx_drug_normalized, idx_drug_original, idx_therapy_line, idx_val_verdict, idx_confidence, idx_atc_code, idx_diagnosis, idx_pregnancy, idx_renal, idx_review_status

**Transactions:** save_many() — BEGIN/COMMIT/ROLLBACK, no partial commits.

---

## 10. Quality Metrics

### Validation verdicts (2675 regimens) — AFTER parser improvements (Tasks 1-4)
| Verdict | Count | % | Baseline % | Δ |
|---------|-------|---|-----------:|---:|
| PASS | 1039 | 38.8% | 32.9% | +159 |
| REVIEW | 443 | 16.6% | 12.0% | +123 |
| REJECT | 1193 | 44.6% | 55.1% | -282 |
| Confidence mean | 0.7188 | — | 0.6312 | +0.0876 |
| Parser errors | 0 | — | 20 | -20 |

### Confidence distribution (after Tasks 1-4)
| Range | Baseline | After |
|-------|---------|------:|
| 0.2-0.4 | 553 | 406 |
| 0.4-0.6 | 428 | 280 |
| 0.6-0.8 | 914 | 643 |
| 0.8-1.0 | 780 | 1346 |

### Top issues (after Tasks 1-4)
| Code | Baseline | After | Severity |
|------|---------:|------:|----------|
| REQUIRED_MISSING | 2869 | 2395 | ERROR |
| DRUG_UNKNOWN | 1166 | 1166 | REVIEW |
| ROUTE_UNKNOWN | 935 | 935 | REVIEW |
| DOSE_UNIT_UNKNOWN | 23 | 23 | REVIEW |
| DURATION_OUT_OF_RANGE | 6 | 12 | WARNING |
| DOSE_OUT_OF_RANGE | 3 | 3 | WARNING |
| COMBINATION_MISSING_COMPONENTS | 7 | 1 | REVIEW |

---

## 11. Known Limitations

1. **44.6% REJECT rate** (down from 55.1%) — 80.6% of remaining REJECT is LLM extraction gaps (961 LLM-only)
2. **441 unknown drugs** — dictionary gaps → drives REVIEW (1166 DRUG_UNKNOWN, 438 drug-only flippable)
3. **0% ATC coverage** — no drug→ATC mapping in dictionary
4. **Parser errors: 0** ✅ (fixed in Task 4, was 20)
5. **Mock validation** — 164 IDs have mock confidence 1.0 (real validation pending)
6. **67 A+B IDs not extracted** — DeepSeek can't handle some PDFs
7. **No golden case tests** — app dose calculation not verified
8. **SQLite** — sufficient for 2675, needs PostgreSQL for >10k

## 12. Current Blockers

| Blocker | Severity | Fix | Measured status |
|---------|----------|-----|-----------------|
| LLM extraction gaps | Critical | Improve prompt + re-extract | 961 LLM-only REJECT (80.6% of REJECT) |
| Dictionary gaps (441 drugs) | High | Expand DRUG_SYNONYMS | 438 drug-only REVIEW flippable → PASS |
| No ATC mapping | Medium | Add DRUG_ATC dict | optional field, confidence only |
| Parser gaps | Low (exhausted ~71%) | Edge-case patterns | 118 parser-flippable REJECT remain (diminishing returns) |

## 13. Next Priorities (per measured Quality Gate)

### Critical (REVIEW↓ + PASS↑, low cost) — NEXT
1. **DRUG_SYNONYMS expansion** (~60 synonyms) — 438 drug-only REVIEW → PASS, REVIEW 16.6%→~2-5%
2. **DRUG_ATC mapping** (~75 drugs → ATC codes) — ATC 0%→~80%, confidence↑

### High (REJECT↓, high cost) — separate project v0.6
3. **LLM re-extraction** (improve prompt, re-run 294 PDF) — 961 LLM-only REJECT, only path to REJECT 25%

### Medium
4. Remaining parser edge cases (118 parser-flippable, diminishing returns)
5. Drug groups handling (фторхинолоны → ATC group)
6. Combination drug normalization ([...] brackets)
7. Typo correction
8. Real LLM validation (replace mock, 130 IDs)
9. Golden case tests (app)

### Low
10. PostgreSQL migration (for >10k)
11. Multiprocessing (for >50k)
12. CI/CD pipeline

**Прогноз (после dictionary + ATC):** REVIEW 16.6%→~2-5%, PASS 38.8%→~55%, ATC 0%→~80%, confidence↑
**REJECT 44.6%→25% (цель) — требует LLM re-extraction (task 3, v0.6).**
**См. `quality_audit_after_parsers.md` для measured comparison.**

---

## 14. Development Rules

### Что НЕЛЬЗЯ менять
- `medical_normalizer/` architecture — FROZEN (не рефакторить)
- `medical_normalizer/models.py` — без веской причины
- `medical_normalizer/confidence.py` — accepted, не трогать
- `medical_normalizer/validator.py` — accepted, не трогать
- `medical_normalizer/normalizer.py` — accepted, не трогать
- `medical_normalizer/db.py` — accepted, не трогать
- `schema.json` (db/) — без обсуждения
- Архитектура single-page HTML — без веской причины
- Латинский формат рецепта — согласовано
- `extraction_raw.json` — не модифицировать
- `knowledge_base.json` — не модифицировать
- `prefilter_rules.json` — осторожно

### Что МОЖНО менять (current phase)
- `medical_dictionary/*.json` — source of truth (add new synonyms, ATC mappings, routes, units; accepted candidates only after manual review)
- `medical_normalizer/dictionary.py` — data-loading layer only (class logic FROZEN)
- `medical_normalizer/frequency_parser.py` — add new patterns (additions only)
- `medical_normalizer/duration_parser.py` — add new patterns (additions only)
- `medical_normalizer/therapy_line_parser.py` — add new mappings (additions only)
- `medical_normalizer/drug_parser.py` — fix parser errors (type guards), add ATC lookup
- `medical_normalizer/dose_parser.py` (in drug_parser.py) — fix parser errors (type guards)
- Documentation files (*.md)

### Review policy (dictionary candidates)
- `medical_dictionary/dictionary_candidates.json` — 441 candidates, all `pending_review`
- **Никогда не auto-accept.** Человек ревьюит → `accepted`/`rejected` статус в JSON
- Только `accepted` entries добавляются в `drug_synonyms.json` / `drug_atc.json`

### Порядок работы (pipeline)
1. Убедиться, что LLM-провайдер отвечает 200
2. `python -m src.pipeline.main extract_raw` — resume-safe
3. `python -m src.pipeline.main validate` — skip done IDs
4. `python -m src.pipeline.main knowledge` — пересборка KB
5. `python main.py doctor` — health check
6. `python -m src.pipeline.prefilter --dry-run` — если изменился clinrecs.json

### Тесты
```
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $py -m pytest medical_normalizer/tests/ -q    # 823 tests
& $py -m pytest src/tests/ -q                     # 39 tests (pipeline)
```

### Для отката
- `python -m src.pipeline.prefilter --restore`

---

## 15. How Another AI Should Continue

### Если задача — dictionary expansion:
1. Прочитай `medical_dictionary/dictionary_candidates.json` — 441 candidates (status: pending_review)
2. Прочитай `medical_dictionary/unknown_drugs.csv` — полный список ranked
3. Прочитай `dictionary_expansion.md` — готовые рекомендации
4. **Внимание:** никогда не auto-accept. Только человек ревьюит → `accepted`/`rejected`
5. Принятые entries → `medical_dictionary/drug_synonyms.json` (synonym→canonical)
6. Принятые ATC → `medical_dictionary/drug_atc.json` (canonical→ATC)
7. DrugParser ATC lookup (через `_coerce_str` helper)
8. Запусти `pytest medical_normalizer/tests/ -q` — все 823 должны пройти
9. Перезапусти quality audit, сравни результаты

### Если задача — parser improvement:
1. Прочитай `quality_report.md` Section 14 (root cause analysis)
2. Добавь patterns в соответствующий parser (additions only)
3. Запусти тесты — все 823 должны пройти
4. Перезапусти quality audit

### Если задача — extraction improvement:
1. Прочитай `PROJECT_STATE.md` (LLM provider section)
2. Проверь API: `python main.py doctor`
3. Запусти `python -m src.pipeline.main extract_raw` (resume-safe)
4. Пересобери KB: `python -m src.pipeline.main knowledge`

### Если задача — new feature:
1. **СТОП.** Architecture FROZEN. Сначала обсудить с человеком.
2. Прочитай `DECISIONS.md` — почему текущая архитектура такая
3. Если feature валидна — добавить через composition, не modification

### General:
- **Всегда** запускай тесты перед commit: `pytest medical_normalizer/tests/ -q`
- **Никогда** не модифицируй FROZEN модули
- **Всегда** документируй решения в `DECISIONS.md`
- **Всегда** логируй работу в `AI_LOG.md`
- **Всегда** обновляй `PROJECT_STATE.md` после значимых изменений

**Future work rule (P4+):** Every new recommendation (e.g. new engine, layout, table) must be accompanied by a separate validation/audit prompt. Cycle: 1. Analysis + design. 2. Implementation. 3. Production validation with real runs on corpus. 4. Update all fixing docs (ROADMAP, PROJECT_STATE, AGENTS, DECISIONS, AI_LOG, extraction docs). 5. Final readiness report with criteria.
