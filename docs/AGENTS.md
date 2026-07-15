# AGENTS.md — ANTIBIO (unified: pipeline + calculator)

> **Последнее обновление:** 2026-07-08
> **Статус:** Перенос pipeline из clinrec_downloader в ANTIBIO

---

## Кратко

ANTIBIO — единый проект для создания и использования базы знаний по антибиотикотерапии из КР МЗ РФ.

Состоит из двух компонентов:

1. **Pipeline** (Python 3.12) — скачивание PDF, извлечение текста, детекция антибиотиков, A/B/C/D классификация, LLM-извлечение схем лечения, валидация, генерация knowledge_base.json + SQLite
2. **HTML-калькулятор** (antibiotic_calc.html) — single-page приложение для расчёта доз по верифицированным схемам (28 препаратов, 46 нозологий)

Pipeline-код перенесён из `C:\clinrec_downloader\` в `src/pipeline/` (14 модулей, 47 тестов). Данные (PDF, SQLite, JSON) остаются в `C:\clinrec_downloader\` (config.py → BASE_DIR).

---

## Структура проекта

```
C:\ANTIBIO/
├── docs/                          # Документация pipeline (эта папка)
│   ├── AGENTS.md                  # Этот файл
│   ├── PROJECT_STATE.md           # Статус pipeline
│   ├── NEXT_TASK.md               # Следующая задача
│   ├── AI_LOG.md                  # Журнал
│   └── DECISIONS.md               # Архитектурные решения
├── src/                           # Python pipeline (переносится)
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── main.py                # CLI
│   │   ├── config.py              # Константы
│   │   ├── api_client.py          # API Минздрава
│   │   ├── downloader.py          # Скачивание PDF
│   │   ├── extractor.py           # Извлечение текста (PyMuPDF)
│   │   ├── analyzer.py            # Детекция антибиотиков
│   │   ├── classifier.py          # A/B/C/D классификация
│   │   ├── section_detector.py    # Поиск разделов лечения
│   │   ├── normalizer.py          # Нормализация названий АБ
│   │   ├── antibiotic_gate.py     # Фильтр антибиотиков
│   │   ├── extractor_llm.py       # LLM извлечение + валидация
│   │   ├── database.py            # SQLite + JSON хранение
│   │   ├── progress.py            # Incremental reprocessing
│   │   └── reporter.py            # Финальный отчёт
│   └── tests/                     # Pytest (39 тестов)
│       ├── conftest.py
│       ├── test_section_detector.py
│       ├── test_classifier.py
│       ├── test_normalizer.py
│       ├── test_extractor_llm.py
│       ├── test_database.py
│       ├── test_progress.py
│       └── test_antibiotic_gate.py
├── db/                            # Данные (существующие)
│   ├── index.json                 # Drugs reference
│   ├── schema.json                # JSON Schema
│   ├── build_db.ps1               # Сборка БД
│   ├── validate_db.js             # Валидация
│   └── diseases/*.json
├── antibiotic_calc.html           # HTML-калькулятор (существующий)
├── antibiotic_calc.html.template  # Шаблон
├── build_html.ps1                 # Сборка HTML
├── server.js                      # Локальный сервер
├── README.md
└── AGENTS.md                      # (legacy — см. docs/AGENTS.md)
```

## Pipeline

```
API Минздрава (apicr.minzdrav.gov.ru)
    ↓
downloader — скачивание PDF (963 файла)
    ↓
extractor — извлечение текста (PyMuPDF + OCR)
    ↓
analyzer — детекция антибиотиков (regex)
    ↓
classifier — A/B/C/D классификация (rule-based)
    ↓
section_detector — извлечение релевантных страниц
    ↓
extract_raw — LLM извлечение схем (DeepSeek V4 Pro)
    ↓
validate — LLM валидация (GLM 5.2)
    ↓
knowledge — генерация knowledge_base.json + SQLite
    ↓
verify — финальный отчёт
```

## Текущее состояние

### Pipeline (из clinrec_downloader) — ✅ перенесён в src/

| Компонент | Статус | Тесты |
| API client | ✅ Ready | — |
| Downloader | ✅ Ready | — |
| Text extractor | ✅ Ready | — |
| Analyzer (regex antibiotics) | ✅ Ready | — |
| Classifier (A/B/C/D) | ✅ Ready | 7 tests |
| Section detector | ✅ Ready | 5 tests |
| Antibiotic gate | ✅ Ready | 8 tests |
| Normalizer (Ru→Lat) | ✅ Ready | 6 tests |
| LLM extraction | ✅ Ready | 8 tests |
| LLM validation | ✅ Ready | — |
| Database (SQLite + JSON) | ✅ Ready | 5 tests |
| Progress (SHA256 tracking) | ✅ Ready | 8 tests |
| Reporter | ✅ Ready | — |
| **Всего** | **14 модулей** | **47 тестов** |

### HTML-калькулятор (существующий)

| Компонент | Статус |
|-----------|--------|
| База препаратов (28 шт) | ✅ 85% |
| База нозологий (46 шт) | ✅ 85% |
| UI (поиск, расчёт, рецепт, история, тема) | ✅ 100% |
| Латинский рецепт при печати | ✅ 100% |
| Клиентская валидация БД | ✅ 100% |
| Тесты | ❌ Нет |

## Что НЕЛЬЗЯ менять

- `db/schema.json` — без обсуждения
- `drugs_reference` в `db/index.json` — только точечные исправления после верификации
- Латинский формат рецепта — согласовано, не откатывать
- Архитектура single-page HTML — без веской причины

## Порядок работы

1. Прочитать: `docs/AGENTS.md` → `docs/PROJECT_STATE.md` → `docs/NEXT_TASK.md` → `docs/AI_LOG.md` → `docs/DECISIONS.md`
2. Аудит перед любой задачей
3. Не создавать код, если аналог существует (искать в src/, db/, antibiotic_calc.html.template)
4. После задачи: обновить `docs/PROJECT_STATE.md`, `docs/AI_LOG.md`, `docs/NEXT_TASK.md`
5. Запустить тесты перед завершением

## Известные проблемы

- LLM извлечение НЕ запущено на реальных PDF (требует API-вызовов, 521 PDF × 2 вызова)
- 107 PDF не скачаны из 2000 (97 null Name + 10 ошибок)
- Python 3.12 НЕ на PATH — нужен полный путь
- HTML-калькулятор не имеет тестов
- `validate_db.js` требует Node.js
