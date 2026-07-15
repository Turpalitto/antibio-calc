# ANTIBIO — Clinical Knowledge Platform

Current status (2026-07-15): P5.6 Clinical Review Workbench implemented, local-only, Clinical Engine disconnected. Queue contains 9,153 physician-review tasks; no object is physician-approved automatically. P5.6 remains open pending credential rotation and Git reproducibility recovery; P6 is blocked. See `P5.6_PRODUCTION_RECOVERY_REPORT.md`.

Единый проект для создания и использования базы знаний по антибиотикотерапии из клинических рекомендаций Минздрава РФ.

## Компоненты

### 1. Pipeline (Python 3.12)
Скачивание PDF → извлечение текста → A/B/C/D классификация → LLM извлечение схем → валидация → knowledge_base.json + SQLite

```
cd src/pipeline
python main.py classify    # A/B/C/D классификация
python main.py extract_raw # LLM извлечение (521 PDF, Level A+B)
python main.py validate    # LLM валидация
python main.py knowledge   # Генерация knowledge_base.json
python main.py verify      # Финальный отчёт
```

### 2. Medical Normalizer (Python 3.12)
Нормализация извлечённых regimens в структурированные объекты с confidence + validation.

```
medical_normalizer/
├── models.py              # NormalizedRegimen, ParserResult, ConfidenceScore
├── dictionary.py          # DRUG_SYNONYMS, ROUTE_SYNONYMS, UNIT_NORMALIZATION
├── drug_parser.py         # DrugParser, DoseNormalizer
├── dose_parser.py         # (in drug_parser.py: DoseNormalizer)
├── route_parser.py        # RouteParser
├── frequency_parser.py    # FrequencyParser
├── duration_parser.py     # DurationParser
├── population_parser.py   # AgeParser, PregnancyParser, GFRParser
├── therapy_line_parser.py # TherapyLineParser
├── confidence.py          # ConfidenceCalculator (weighted confidence)
├── validator.py           # Validator (PASS/REVIEW/REJECT)
├── normalizer.py          # MedicalNormalizer (single entry point)
├── db.py                  # NormalizerDB (SQLite persistence)
└── tests/                 # 726 tests (99.9% coverage)
```

**Usage:**
```python
from medical_normalizer.normalizer import MedicalNormalizer
result = MedicalNormalizer.normalize(raw_dict)
# result.regimen, result.confidence, result.validation
```

### 3. HTML-калькулятор
Single-page приложение для расчёта доз антибиотиков (72 нозологии, 40 препаратов).

Открыть `antibiotic_calc.html` в браузере.

## Структура

```
C:\ANTIBIO/
├── medical_normalizer/     # Medical Normalizer (13 модулей, 726 тестов)
├── src/pipeline/           # Python pipeline (13 модулей)
├── src/tests/              # 39 тестов pytest (pipeline)
├── src/llm/                # LLM провайдеры
├── db/                     # Данные калькулятора (JSON)
├── antibiotic_calc.html    # Готовое приложение
├── antibiotic_calc.html.template  # Шаблон
├── build_html.ps1          # Сборка HTML
├── server.js               # Локальный сервер (http://0.0.0.0:8080)
├── quality_report.md       # Quality Audit отчёт
├── field_statistics.csv    # Статистика по полям
├── unknown_drugs.csv       # 441 неизвестный препарат
├── dictionary_expansion.md # Рекомендации по словарю
├── production_readiness.md # Оценка готовности
├── PROJECT_STATE.md        # Состояние проекта
├── AI_LOG.md               # Лог работы AI
├── NEXT_TASK.md            # Следующие задачи
├── DECISIONS.md            # Архитектурные решения
└── AGENTS.md               # Project overview for AI agents
```

## Текущее состояние

- **Pipeline:** извлечение завершено (294 guidelines, 2675 regimens)
- **Medical Normalizer:** COMPLETE (726/726 tests, 99.9% coverage)
- **Quality Audit:** завершён (PASS 33%, REVIEW 12%, REJECT 55%)
- **Фаза:** Medical Data Quality Improvement

## Источник данных

API Минздрава РФ: https://apicr.minzdrav.gov.ru
- 2000 клинических рекомендаций
- 963 уникальных PDF скачано
- 294 guidelines с антибиотиками экстрагировано
- 2675 regimens в knowledge_base.json

## Технологии

- Python 3.12, PyMuPDF, httpx, orjson, SQLite
- DeepSeek V4 Flash (извлечение), opencode.ai/zen
- Medical Normalizer: dataclasses, frozen configs, parameterized SQL
- HTML/CSS/JS (калькулятор)

## Python

```
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $py -m pytest medical_normalizer/tests/ -q   # 726 tests
& $py src/pipeline/main.py verify               # Pipeline health check
```

## Документация

- `AGENTS.md` — полный overview проекта для AI agents
- `PROJECT_STATE.md` — текущее состояние
- `quality_report.md` — quality audit
- `production_readiness.md` — readiness assessment
- `dictionary_expansion.md` — рекомендации по словарю

## BundleManifest (P0-1)

JSON Schema + validator for knowledge bundles (RegimenBundle, SafetyBundle, etc.).

- Schema: `clinical_engine/resources/bundle_manifest.schema.json`
- Usage:
  ```python
  from clinical_engine.manifest import load_manifest, validate_manifest
  m = load_manifest("path/to/manifest.json")
  validate_manifest(raw_dict)
  ```
- Examples: regimen_bundle_manifest.json, safety_*, terminology_*, score_profile_* in resources/
- I10: unknown optional fields are ignored (forward compatibility).
- Version axes: schema_version, version, requires_kernel, bundle_format.
- See DEVELOPMENT_BACKLOG.md for P0-1 DoD and dependencies.
