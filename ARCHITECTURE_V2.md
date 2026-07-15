# ARCHITECTURE V2 — Domain-Agnostic Research Paper Platform

> **Статус:** План (не реализовано)
> **Цель:** Рефакторинг после выхода v1.0
> **Принцип:** Сначала закончить продукт, потом улучшать архитектуру.

---

## Текущая архитектура (v1)

```
main.py                      # CLI entry (doctor — health check)
antibiotic_calc.html         # Отдельное приложение (НЕ трогать)
src/
├── pipeline/                # Всё завязано на антибиотики
│   ├── antibiotic_gate.py   # Медицинская логика
│   ├── config.py            # ATC-коды, названия АБ, тени
│   ├── extractor_llm.py     # Промпты для LLM жёстко про АБ
│   ├── prefilter.py         # Правила только для КР МЗ РФ
│   └── ...
├── llm/                     # Хорошая абстракция (универсальная)
│   └── providers/*.py       # 8 бэкендов — можно расширять
└── tests/                   # Тесты завязаны на АБ
```

**Проблема:** 90% кода в `src/pipeline/` содержит медицинскую специфику. Нельзя переиспользовать для AI, физики, химии и т.д.

---

## Целевая архитектура (v2)

```
main.py                      # CLI entry (generic)
core/                        # Доменно-независимое ядро
├── pipeline/                # Абстрактный pipeline
│   ├── base.py              # Базовые классы (Stage, Pipeline, Config)
│   ├── downloader.py        # Загрузка PDF/articles (универсальный)
│   ├── extractor.py         # Извлечение текста из PDF
│   ├── section_detector.py  # Поиск разделов (гибкие паттерны)
│   ├── normalizer.py        # Нормализация данных (generic)
│   ├── progress.py          # Чекпоинты (уже универсально)
│   └── reporter.py          # Отчёты (уже универсально)
├── llm/                     # LLM-абстракция (уже универсально)
│   ├── core.py              # Provider chain, caching, fallback
│   └── providers/           # 8+ бэкендов
└── storage/                 # Работа с данными
    ├── file_store.py        # PDF/raw/processed storage
    ├── manifest.py          # movement_manifest
    └── database.py          # SQLite/KB

plugins/                     # Подключаемые модули (опционально)
├── medicine/                # Медицинский плагин (текущий pipeline)
│   ├── gate.py              # antibiotic_gate (domain filter)
│   ├── config.py            # ATC-коды, названия АБ
│   ├── extractor.py         # Промпты для АБ
│   ├── prefilter_rules.json # Правила фильтрации
│   ├── knowledge.py         # knowledge_base сборка
│   └── ...
├── ai/                      # AI/ML плагин (пример)
│   ├── gate.py              # Фильтр ML-статей
│   ├── config.py            # Терминология AI
│   ├── extractor.py         # Промпты для ML
│   └── ...
├── chemistry/               # Плагин для химии
├── physics/
└── law/
```

---

## Принципы

### 1. Core не знает о доменах
- `core/` не импортирует `plugins/`
- Все конфиги доменов — в плагинах
- Pipeline stages — абстрактные классы, конкретная логика — в плагинах

### 2. Plugin = набор override'ов
Каждый плагин содержит:
- `gate.py` — как отфильтровать релевантные статьи (prefilter)
- `config.py` — терминология, промпты, паттерны
- `extractor.py` — LLM-промпты для извлечения данных (если отличается от generic)
- `knowledge.py` — как собрать knowledge_base
- `prefilter_rules.json` — правила для gate
- `tests/` — тесты плагина

### 3. CLI-диспетчеризация
```
python main.py doctor        # Health check (generic, v1)
python main.py pipeline medicine download     # Загрузка статей по медицине
python main.py pipeline medicine extract_raw  # Извлечение схем лечения
python main.py pipeline ai extract_raw        # Извлечение ML-архитектур
python main.py plugin list                    # Список установленных плагинов
python main.py plugin install ai              # Установка AI-плагина
```

### 4. Изоляция тестов
- `tests/core/` — тесты ядра (доменно-независимые)
- `plugins/medicine/tests/` — тесты медицинского плагина
- `plugins/ai/tests/` — тесты AI-плагина

### 5. LLM-провайдеры — не плагины, часть core
LLM-провайдеры (Anthropic, DeepSeek, OpenAI, Gemini, Ollama и т.д.) — это инфраструктура, а не доменная логика. Они остаются в core. Новый провайдер = новый файл в `core/llm/providers/`.

---

## Миграция v1 → v2

### Этапы

1. **Выделить core:** переместить доменно-независимый код (llm/, database.py, progress.py, reporter.py, downloader.py)
2. **Создать plugin-интерфейсы:** базовые классы в core/pipeline/base.py
3. **Переместить medical код в plugins/medicine/:**
   - antibiotic_gate.py → gate.py
   - специфичный config.py → plugins/medicine/config.py
   - extractor_llm.py → плагин-специфичный extractor
   - prefilter.py + prefilter_rules.json → plugins/medicine/
4. **Обновить CLI:** main.py с диспетчеризацией по доменам
5. **Проверить:** `python main.py pipeline medicine doctor` → тот же health check
6. **Удалить старые файлы:** после верификации, что всё работает

### Риски
- **Совместимость:** movement_manifest, extraction_*.json — должны остаться на месте (данные)
- **Тесты:** все существующие тесты должны проходить после рефакторинга
- **Зависимости:** plugins/medicine может тянуть дополнительные пакеты (pymorphy2, etc.)

---

## Плагины после v1

### Приоритет (после medicine):
1. AI (ML conference papers: архитектуры, датасеты, метрики)
2. Chemistry (молекулы, реакции, свойства)
3. Physics (формулы, константы, эксперименты)
4. Law (законы, статьи, прецеденты)
5. Finance (отчёты, показатели, регуляции)

Каждый плагин — отдельный PR с review.

---

## Нерешённые вопросы

- Как деплоить плагины? Pip package? Git submodule? Просто папка?
- Версионирование knowledge_base: одна на домен или общая?
- Как быть с overlapping content (междисциплинарные статьи)?
- Как тестировать core без плагинов?
- CI/CD: GitHub Actions для core + матрица для плагинов?
