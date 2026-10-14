# ANTIBIO — Clinical Knowledge Platform

Current status (2026-10-14): calculator shell completed after the independent
audit `docs/audits/AUDIT_2026-10-14.md` — 120 nosologies, **65 computable /
55 blocked until owner verification**, patient context (age, pregnancy, GFR)
with advisory safety flags, golden-case tests, loopback-only engine API.
P5.6 Clinical Review Workbench is local-only, Clinical Engine disconnected; no
object is physician-approved automatically; P6 is blocked. Working docs:
`PROJECT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`, `AI_LOG.md`.

## Setup

```
uv python install 3.12                               # requires-python = ">=3.12,<3.13"
uv sync --frozen --extra clinical --extra tests      # creates .venv from uv.lock
npm install                                          # no runtime deps; node ≥ 22 for db/validate_db.js
.venv/bin/python -m pytest -q                        # testpaths from pyproject.toml
npm run validate                                     # node db/validate_db.js
```

CI (`.github/workflows/ci.yml`) runs exactly these steps on Python 3.12 /
Node 24. `pytest` on another Python (e.g. 3.11) works for the test suite but
`uv sync --frozen` refuses it — use a manual venv in that case.

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
Single-page приложение для расчёта доз антибиотиков (120 нозологий, 47 препаратов;
65 записей расчётные, 55 закрыты до врачебной верификации — см. бейджи
«КР МЗ РФ» / «БЕЗ КР» / «ЗАБЛОКИРОВАНО» в интерфейсе).

Входы: вес, возраст (д/нед/мес/лет → автоматическая возрастная группа),
беременность/лактация, СКФ. Флаги по `age_restriction_min`,
`pregnancy_category`, `renal_adjustment` — предупреждающие (красный/янтарный),
несоответствие веса возрастной группе блокирует расчёт.

Клиническая БД встроена в `antibiotic_calc.html` на этапе сборки, поэтому для
расчёта доз API не нужен. Сборка и запуск:

```
python db/build_db.py            # db/diseases/*.json + db/index.json → db/antibio_db.json (+ source gate, + validate)
npm run validate                 # node db/validate_db.js (0 errors обязательны; warnings = owner review)
npm run build                    # db/build_html.py: template + db/ → antibiotic_calc.html, штампует sw.js CACHE_VERSION
npm start                        # = node server.js → http://127.0.0.1:8080
```

`server.js` отдаёт только allowlist файлов (`/`, `/antibiotic_calc.html`,
`/sw.js`, `/manifest.webmanifest`, `/favicon.ico`, `/icons/*`, `/vendor/*`) и
проксирует `/v1/`, `/v2/` на клинический движок в режиме реального времени
(никогда не кэширует). Переменные окружения:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `8080` | адрес оболочки; `HOST=0.0.0.0` открывает LAN только для статики |
| `ENGINE_BASE_URL` или `ENGINE_HOST`+`ENGINE_PORT` | `http://127.0.0.1:8000` | адрес движка для прокси |
| `ENGINE_TIMEOUT_MS` | `15000` | таймаут запроса к движку (502 `ENGINE_UNAVAILABLE`) |
| `ENGINE_PROXY_ALLOW_LAN` | не задана | `1` — разрешить прокси для не-loopback клиентов (по умолчанию 403 `PROXY_LOOPBACK_ONLY`) |
| `ENGINE_MAX_BODY_BYTES` | `1048576` | лимит тела запроса к прокси (413 `PAYLOAD_TOO_LARGE`) |

Движок (`/v1/recommend`, `/v2/*`) сам принимает только loopback-пиров и
учитывает `X-Forwarded-For`, который добавляет прокси.

Альтернатива — сам движок FastAPI, тогда статику PWA отдаёт он:

```
uvicorn clinical_engine.api.app:app --port 8000   # http://127.0.0.1:8000/personal
```

Порт 8000 — это и дефолт uvicorn, и `ENGINE_PORT` в `server.js`; обе стороны
согласованы. `uvicorn` входит в необязательный extra `clinical`
(`pip install -e '.[clinical]'`) и в `.venv` репозитория **не установлен** —
`fastapi` установлен, сервер нужен отдельно. Прокси `/v1`, `/v2` из
`server.js` в этом режиме не используется.

Ни то, ни другое не обязательно: `antibiotic_calc.html` открывается и напрямую
из файловой системы (file://), но тогда service worker не регистрируется
(браузер запрещает его для file://) и офлайн-режим недоступен.

## Структура

```
antibio-calc/
├── medical_normalizer/     # Medical Normalizer (13 модулей, 1155 тестов)
├── clinical_engine/        # Clinical Decision Engine (api/, stages/, personal/, tests/)
├── src/pipeline/           # Python pipeline (13 модулей)
├── src/tests/              # 409 тестов pytest (pipeline)
├── src/llm/                # LLM провайдеры
├── db/                     # Данные калькулятора (JSON) + build_html.py + validate_db.js
├── antibiotic_calc.html    # Готовое приложение (артефакт сборки)
├── antibiotic_calc.html.template  # Шаблон
├── sw.js                   # Service worker (офлайн-оболочка)
├── manifest.webmanifest    # PWA-манифест
├── icons/                  # PWA-иконки 192/512
├── package.json            # scripts: start / build / validate / test
├── server.js               # Локальный сервер + прокси движка (http://127.0.0.1:8080)
├── quality_report.md       # Quality Audit отчёт
├── medical_dictionary/unknown_drugs.csv  # 441 неизвестный препарат
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
- **Medical Normalizer:** COMPLETE (1155 tests collected, 99.9% coverage)
- **Clinical Engine:** API v1 + v2 (personal physician, loopback-only), PWA assets
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
.venv/bin/python -m pytest -q                         # testpaths из pyproject.toml; 2026-10-14: 2660 passed, 30 skipped
.venv/bin/python -m pytest clinical_engine/tests/test_calculator_dose_golden.py -q   # golden-кейсы калькулятора
.venv/bin/python -m pytest tests -q                   # архив RC030-инструментов (вне testpaths): 404 passed
PYTHONPATH=.:src/pipeline:src .venv/bin/python src/pipeline/main.py verify   # Pipeline health check
```

Тестовые команды в этом файле и в `AGENTS.md` используют `.venv/bin/python`
репозитория. `pytest` без путей берёт `testpaths` из `pyproject.toml`
(`medical_normalizer/tests`, `clinical_engine/tests`,
`clinical_engine/regimen/tests`, `clinical_engine/review_workbench/tests`,
`src/tests`).

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
