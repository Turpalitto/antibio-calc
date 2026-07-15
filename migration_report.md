# Migration Report: clinrec_downloader → ANTIBIO

**Дата:** 2026-07-08
**Аудитор:** OpenCode

---

## Вывод: ПРОЕКТЫ НЕ ПЕРЕСЕКАЮТСЯ

**clinrec_downloader** — Python pipeline для скачивания PDF клинических рекомендаций с API Минздрава и извлечения схем лечения (предназначен для Flutter-приложения DOSA).

**ANTIBIO** — single-page HTML калькулятор доз антибиотиков с ручной верификацией БД.

Ни один файл не существует в обоих проектах с одинаковым именем и путём. Файлы с одинаковым именем (`AGENTS.md`) имеют разное содержимое и разный контекст.

---

## Полный инвентарь

### ANTIBIO (13 файлов, без .git и .claude)

| Файл | Тип | Назначение |
|------|-----|-----------|
| `antibiotic_calc.html.template` | Шаблон | Основной код приложения (HTML+CSS+JS) |
| `antibiotic_calc.html` | Сборка | Собранное приложение (template + DB) |
| `build_html.ps1` | Скрипт | Сборка HTML из шаблона |
| `server.js` | Node.js | Локальный сервер для превью |
| `AGENTS.md` | Документация | Правила для AI-агентов |
| `PROJECT_STATE.md` | Документация | Статус проекта |
| `NEXT_TASK.md` | Документация | Следующая задача |
| `AI_LOG.md` | Документация | Журнал |
| `DECISIONS.md` | Документация | Архитектурные решения |
| `db/index.json` | Данные | Meta + drugs_reference |
| `db/schema.json` | Схема | JSON Schema БД |
| `db/build_db.ps1` | Скрипт | Сборка БД |
| `db/validate_db.js` | Node.js | Валидация БД |
| `db/diseases/*.json` (9) | Данные | Нозологии по категориям |
| `db/antibio_db.json` | Данные | Собранная БД (генерируется) |

### clinrec_downloader (без node_modules, downloads, __pycache__)

#### Python (33 файла)

| Файл | Назначение | Статус |
|------|-----------|--------|
| `main.py` | CLI: download\|analyze\|classify\|... | Готов |
| `config.py` | Константы, API URLs, списки АБ | Готов |
| `api_client.py` | ClinrecApi | Готов |
| `downloader.py` | Скачивание PDF | Готов |
| `extractor.py` | Извлечение текста из PDF (PyMuPDF) | Готов |
| `analyzer.py` | Детекция антибиотиков (regex) | Готов |
| `classifier.py` | A/B/C/D классификация | Готов |
| `section_detector.py` | Детекция разделов лечения | Готов |
| `normalizer.py` | Нормализация названий АБ | Готов |
| `extractor_llm.py` | LLM извлечение (DeepSeek) | Готов |
| `extractor.py` | Базовая экстракция | Готов |
| `antibiotic_gate.py` | Фильтр антибиотиков | Готов |
| `database.py` | SQLite + JSON хранение | Готов |
| `reporter.py` | Финальный отчёт | Готов |
| `progress.py` | Incremental reprocessing | Готов |
| `tests/conftest.py` | Pytest конфиг | Готов |
| `tests/test_section_detector.py` | 5 тестов | Готов |
| `tests/test_progress.py` | 8 тестов | Готов |
| `tests/test_normalizer.py` | 6 тестов | Готов |
| `tests/test_extractor_llm.py` | 8 тестов | Готов |
| `tests/test_database.py` | 5 тестов | Готов |
| `tests/test_classifier.py` | 7 тестов | Готов |
| `tests/test_antibiotic_gate.py` | Тесты | Готов |
| `tests/__init__.py` | Пакет | Готов |
| `_*.py` (8 файлов) | Debug/скрап | Черновик |

#### Документация (6 файлов)

| Файл | Назначение |
|------|-----------|
| `docs/PROJECT_STATE.md` | Статус pipeline |
| `docs/NEXT_TASK.md` | Запуск LLM извлечения |
| `docs/AI_LOG.md` | 7 записей |
| `docs/DECISIONS.md` | 11 решений |
| `docs/superpowers/specs/*.md` | Спецификация pipeline |
| `docs/superpowers/plans/*.md` | План |

#### Данные (НЕ переносить)

| Файл | Размер | Назначение |
|------|--------|-----------|
| `clinrecs.json` | 4.4 MB | 2000 записей |
| `metadata.sqlite` | 1.7 MB | SQLite метаданные |
| `antibiotic_guidelines.json` | 2.0 MB | 1235 записей с АБ |
| `downloads_all/` | ~963 PDF | Исходные PDF |
| другие `.json` | ~10 шт | Extraction, progress, review |
| `report.txt` | ~10 KB | Финальный отчёт |

---

## Duplicates / Совпадения

| Имя файла | В clinrec | В ANTIBIO | Статус |
|-----------|-----------|-----------|--------|
| `AGENTS.md` | Правила pipeline | Правила проекта ANTIBIO | **Разные, не объединять** |
| Прочие документы | `docs/` подпапка | В корне проекта | **Разные, не объединять** |

**0 файлов полностью совпадают.**
**0 файлов имеют одинаковое содержимое с разными именами.**

---

## ONLY IN clinrec_downloader (потенциально полезное для ANTIBIO)

### Код для переноса (Python pipeline)

| Файл | Полезность для ANTIBIO | Рекомендация |
|------|------------------------|-------------|
| `classifier.py` | Средняя — классификация КР по релевантности | **Перенести** как утилиту |
| `normalizer.py` | Высокая — нормализация названий АБ (Ru→Lat) | **Перенести** — дополнит LATIN_INN |
| `antibiotic_gate.py` | Средняя — фильтрация АБ | **Перенести** как утилиту |
| `section_detector.py` | Низкая — поиск разделов в PDF | **Не переносить** (специфично для PDF) |

### Документация для интеграции

| Файл | Рекомендация |
|------|-------------|
| `docs/superpowers/specs/2026-07-08-antibiotic-knowledge-base-design.md` | **Не переносить** — специфична для DOSA |
| `docs/superpowers/plans/2026-07-08-antibiotic-knowledge-base.md` | **Не переносить** — специфична для DOSA |

### Тесты

| Файл | Рекомендация |
|------|-------------|
| `tests/` (8 файлов, 39 тестов) | **Скопировать структуру** как образец для ANTIBIO |

---

## ONLY IN ANTIBIO (нет в clinrec)

Все файлы ANTIBIO уникальны — перенос из clinrec не требуется.

---

## Сводка миграции

| Категория | Действие |
|-----------|---------|
| Python-код, полезный для ANTIBIO | `classifier.py`, `normalizer.py`, `antibiotic_gate.py` |
| Структура тестов | Скопировать подход (pytest + conftest) |
| Данные (JSON, SQLite, PDF) | **НЕ переносить** |
| `node_modules/`, `__pycache__/` | **НЕ переносить** |
| Debug-скрипты (`_*.py`) | **НЕ переносить** (черновики) |
| Документация (`docs/`) | **НЕ переносить** (специфична для pipeline) |

---

## План безопасной миграции

```
ШАГ 1 (готов): Аудит — этот отчёт
ШАГ 2 (ожидает подтверждения): Перенос Python-утилит
  ├── src/pipeline/classifier.py      ← из clinrec
  ├── src/pipeline/normalizer.py       ← из clinrec
  ├── src/pipeline/antibiotic_gate.py  ← из clinrec
  └── src/pipeline/__init__.py
ШАГ 3 (ожидает подтверждения): Перенос тестовой инфраструктуры
  ├── tests/conftest.py               ← из clinrec (адаптировать)
  └── tests/ для pipeline             ← из clinrec (адаптировать)
ШАГ 4 (ожидает подтверждения): Перенос документации (опционально)
  └── docs/pipeline/                   ← копия docs/ из clinrec (ссылочно)
```

---

**Итог:** Проекты независимы, пересечений нет. clinrec_downloader — Python pipeline для сбора данных из PDF. ANTIBIO — готовый HTML-калькулятор. Единственная связь: clinrec может генерировать данные, которые пополняют ANTIBIO database. Перенос кода не критичен, но может быть полезен для автоматизации.
