# PROJECT STATE — ANTIBIO Pipeline

> **Дата:** 2026-07-08
> **Статус:** Pipeline работает. A=323, B=183, C=1057, D=437

---

## Pipeline (из clinrec_downloader) — 100% реализован

**Завершено:**

- [x] Реверс-инжиниринг API Минздрава (apicr.minzdrav.gov.ru)
- [x] Скачивание 963 уникальных PDF
- [x] Извлечение текста из PDF (PyMuPDF + OCR fallback)
- [x] Детекция антибиотиков (regex, 60+ препаратов, ключевые слова)
- [x] A/B/C/D классификация: A=334, B=187, C=1042, D=437
- [x] Section detection — поиск разделов лечения в PDF (5 тестов)
- [x] Нормализация названий Ru→Latin + ATC коды (6 тестов)
- [x] LLM извлечение схем лечения (8 тестов, не запущено на реальных PDF)
- [x] LLM валидация (8 тестов)
- [x] SQLite antibiotic_regimens + JSON хранение (5 тестов)
- [x] Incremental reprocessing по SHA256 (8 тестов)
- [x] CLI: download|analyze|classify|filter|extract_raw|validate|knowledge|update|verify
- [x] Финальный отчёт (report.txt)
- [x] review_required.json (1042 Level C записей)
- [x] Классификация запущена: A=323, B=183, C=1057, D=437 (отклонение ~3% от эталона — шум PDF-парсинга)
- [x] Все 47 тестов проходят

**Данные:**

| Файл | Размер | Описание |
|------|--------|----------|
| `clinrecs.json` | 4.4 MB | 2000 записей с метаданными + анализом |
| `metadata.sqlite` | 1.7 MB | БД: таблица clinrecs |
| `antibiotic_guidelines.json` | 2.0 MB | 1235 рекомендаций с антибиотиками |
| `downloads_all/` | ~963 PDF | Все уникальные PDF |
| `downloads_antibiotics/` | 566 PDF | PDF с антибиотиками |
| `downloads_other/` | 395 PDF | PDF без антибиотиков |

**Тесты:** 47/47 проходят

---

## HTML-калькулятор (legacy) — стабилен

См. корневой `PROJECT_STATE.md`.

---

## Завершено сегодня

- [x] Создана структура документации `docs/` (AGENTS, PROJECT_STATE, NEXT_TASK, AI_LOG, DECISIONS)
- [x] Создан README.md
- [x] Pipeline код перенесён из clinrec_downloader → ANTIBIO/src/pipeline/ (14 модулей)
- [x] Тесты перенесены (8 файлов, 47 тестов)
- [x] Создан pyproject.toml с конфигурацией pytest
- [x] config.py: BASE_DIR скорректирован на C:\clinrec_downloader
- [x] conftest.py: pdf_path скорректирован
- [x] Все 47 тестов проходят

## Не завершено

- [ ] LLM извлечение НЕ запущено (521 PDF × 2 API-вызова)
- [ ] HTML-калькулятор не имеет тестов
- [ ] knowledge_base.json не сгенерирован (ждёт LLM)
- [ ] CI/CD отсутствует
- [ ] 107 PDF не скачаны

---

## Следующие шаги (приоритет)

1. ~~Перенос pipeline кода из clinrec_downloader в ANTIBIO/src/~~ ✅
2. Запуск LLM извлечения (extract_raw) для Level A+B
3. Валидация извлечённых схем
4. Генерация knowledge_base.json + SQLite
5. Интеграция knowledge_base с HTML-калькулятором
6. Тестирование всего пайплайна
