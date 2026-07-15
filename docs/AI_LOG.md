# AI LOG — ANTIBIO Pipeline

---

## 2026-07-08: Инициализация проекта ANTIBIO Pipeline

**Задача:** Создание объединённого проекта ANTIBIO (pipeline + HTML-калькулятор)

**Созданные файлы:**
- `docs/AGENTS.md` — главный handover файл
- `docs/PROJECT_STATE.md` — статус pipeline
- `docs/NEXT_TASK.md` — первая задача (перенос кода)
- `docs/AI_LOG.md` — этот журнал
- `docs/DECISIONS.md` — архитектурные решения
- `README.md` — обзор проекта

**История (перенесена из clinrec_downloader):**

### Entry 1: Реверс-инжиниринг API Минздрава
- Найден API: `POST /api.ashx?op=GetJsonClinrecsFilterV2` + `GET /api.ashx?op=GetClinrecPdf&id=<CodeVersion>`
- Скачан test.pdf (835683 байт)

### Entry 2: Создание pipeline скачивания
- Скачано 963 уникальных PDF
- 2000 записей в clinrecs.json
- 107 PDF не скачаны (97 null Name + 10 ошибок)

### Entry 3: Анализ антибиотиков
- 1235 с антибиотиками, 765 без
- 61.8% рекомендаций содержат антибиотики

### Entry 4: Фильтрация + метаданные + отчёт
- SQLite (2000 записей, 1.7 MB)
- antibiotic_guidelines.json (1235 записей, 2.0 MB)

### Entry 5: Дизайн pipeline извлечения
- Спецификация из 10 частей утверждена
- A/B/C/D классификация, section detection, LLM extraction, validation, storage

### Entry 6: Система передачи контекста
- Создана документация для cross-IDE передачи

### Entry 7: Реализация pipeline
- 13 модулей, 39 тестов
- Классификация: A=334, B=187, C=1042, D=437

---

**Проблемы:**
- LLM извлечение не запущено на реальных PDF
- 107 PDF отсутствуют
- HTML-калькулятор без тестов

**Решения:**
- Перенести pipeline код в `src/pipeline/` внутри ANTIBIO
- Документацию вести в `docs/`
- Использовать Python 3.12 по полному пути

---

## 2026-07-08: Перенос pipeline в ANTIBIO (текущая сессия)

**Задача:** Перенести код из clinrec_downloader в ANTIBIO/src/pipeline/

**Что сделано:**
- Создана структура `docs/` с 5 документами + README.md
- 14 Python-модулей перенесены без изменений логики
- 8 тестовых файлов перенесены
- config.py: BASE_DIR скорректирован на C:\clinrec_downloader
- conftest.py: pdf_path скорректирован
- Создан pyproject.toml с конфигурацией pytest
- Все 47 тестов проходят (100%)

**Изменённые файлы:**
- `docs/AGENTS.md` — создан
- `docs/PROJECT_STATE.md` — создан
- `docs/NEXT_TASK.md` — создан
- `docs/AI_LOG.md` — создан
- `docs/DECISIONS.md` — создан
- `README.md` — создан
- `src/pipeline/__init__.py` — создан
- `src/pipeline/config.py` — изменён BASE_DIR
- `src/tests/conftest.py` — изменён pdf_path
- `pyproject.toml` — создан
- 14 .py модулей — перенесены
- 8 тестовых файлов — перенесены

**Тесты:** 47/47 passed (7.15s)

---

## 2026-07-08: Запуск классификации из ANTIBIO

**Задача:** Проверить CLI из нового расположения

**Что сделано:**
- Запущен `main.py classify` из C:\clinrec_downloader\ (CWD) с PYTHONPATH на ANTIBIO
- Классификация: A=323, B=183, C=1057, D=437 (отклонение ~3% от эталона)
- Запущен `main.py verify` — report.txt сгенерирован
- Тесты: 47/47 passed (7.10s)

**Проблемы:**
- Относительные пути pdf_path требуют запуска из C:\clinrec_downloader\
- MuPDF выводит много синтаксических ошибок (легитимные проблемы в PDF, не влияют на результат)
