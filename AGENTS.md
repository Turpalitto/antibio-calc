# AGENTS.md — как работать в ANTIBIO (действующие правила)

> Authority: `GOVERNANCE_SOURCE_OF_TRUTH.md` → `docs/governance/ANTIBIO_CONSTITUTION.md` → этот файл.
> Приоритет истины: репозиторий/код/тесты/реальный прогон → действующие governance-доки → исторические доки → чат.
> Последнее обновление: 2026-10-14. Фаза: калькулятор доведён после аудита 2026-10-14; Clinical Engine
> НЕ подключён к калькулятору; P5.6 — ACCEPTANCE/NOT COMPLETE; P6 — BLOCKED.
> Полная историческая версия этого файла (633 строки: архитектура, статистика, фазы 2026-07…09) —
> `docs/history/AGENTS_2026-10-14_full.md`. Она применяется только там, где не противоречит этому файлу.

## 1. Абсолютные запреты (никаких исключений)

- **Никогда** не подключать Clinical Decision Engine к калькулятору и не выдавать рекомендации движка врачу до P6 entry gates.
- **Никогда** не одобрять медицинский контент автоматически: статус `approved`/«верифицировано по КР», снятие блокировки записи, принятие кандидата словаря — только явное решение владельца-врача, зафиксированное в данных/`DECISIONS.md`.
- **Никогда** не коммитить production DB/PDF корпуса, личные данные пациентов, plaintext credentials (`.env`, ключи провайдеров). Секреты — только в локальном хранилище; `gitleaks` в CI блокирует.
- **Никогда** не фабриковать источник: без `cr_id`/документированного `cr_note` запись остаётся `calculation_blocked`; «КР №—» не выдумывать.
- **Frozen** (не менять логику и не рефакторить «ради стиля»): `medical_normalizer/` (ядро: `models.py`, `confidence.py`, `validator.py`, `normalizer.py`, `db.py`), логика Clinical Decision Engine, детерминированная медицинская логика, схемы bundle, валидированные медицинские данные, `db/schema.json` (без обсуждения), архитектура single-page HTML, латинский формат рецепта, `extraction_raw.json`, `knowledge_base.json`; `prefilter_rules.json` — осторожно.
- **Можно** менять: `medical_dictionary/*.json` (source of truth; новые синонимы/ATC/пути/единицы — только `accepted` после ручного ревью), `medical_normalizer/dictionary.py` (только загрузка данных), `frequency_parser.py` / `duration_parser.py` / `therapy_line_parser.py` (только добавление паттернов), `drug_parser.py` (type guards, ATC lookup), калькулятор (`antibiotic_calc.html.template`, `db/`), pipeline (`src/`), движок вне frozen-логики, тесты, документацию.
- Новая функция = **СТОП**: архитектура FROZEN, сначала обсудить с владельцем; валидная функция добавляется композицией, не модификацией (`DECISIONS.md` объясняет, почему всё устроено так).

## 2. Постоянные законы

**Clinical Traceability Rule.** Каждая видимая врачу рекомендация прослеживаема: какие КР её породили, какие схемы рассматривались, какие safety-фильтры её изменили, какой терминологический маппинг повлиял, какие стадии движка участвовали, почему отвергнуты альтернативы, какие доказательства поддерживают итог. Ни одна рекомендация не может быть чёрным ящиком — врач видит причинную цепочку, а не «ИИ так решил».

**Optimization Rule.** Не оптимизировать инфраструктуру, если это напрямую не улучшает качество клинического решения, безопасность, сопровождаемость или измеримую производительность. Нет измеримой пользы — не трогать.

**Future work rule (P4+).** Каждое новое звено (движок, layout, таблица, источник) сопровождается отдельным validation/audit-промптом. Цикл: анализ и дизайн → реализация → production-валидация реальными прогонами на корпусе → обновление доков (ROADMAP, PROJECT_STATE, AGENTS, DECISIONS, AI_LOG) → финальный readiness-отчёт с критериями.

## 3. Обязательный протокол хендоффа (любая IDE / любой агент)

Вся память проекта живёт в Markdown-файлах корня. Никогда не полагайся на память чата: следующий агент стартует с нуля и прочитает только их. **В конце КАЖДОЙ задачи обнови:**

| Файл | Что записать |
|------|--------------|
| `AI_LOG.md` | Новая запись сверху: дата, что сделано, какие файлы изменены/созданы, ключевые решения, результат тестов. |
| `PROJECT_STATE.md` | Текущее состояние: версия, статус фазы, что готово/нет, результат последнего прогона тестов. |
| `NEXT_TASK.md` | Что делать следующим: конкретные шаги, блокеры, открытые решения владельца. |
| `DECISIONS.md` | Любое нетривиальное решение (архитектурное, по данным, отклонение от спеки) — датированная запись с обоснованием. |

Правила записи: абсолютные факты (пути, функции, команды, версии — не «поправил парсер», а «`clinical_engine/stages/dose_adjustment.py`: убрал dead-код `excluded_here`»); относительные даты → абсолютные; всегда указывать, как проверить (команда + актуальный результат); тесты держать зелёными и фиксировать это.

Онбординг: начать с `HANDOFF.md` (центральный индекс и список обязательного чтения), затем по ссылкам. Онбординг завершён только после явного отчёта по 6 пунктам: Frozen Components, Current Milestone, Active Issue, Workflow Stage, Current Test Status, Next Implementation Step. Неясно — остановись и спроси; не кодить без подтверждения задачи. Ждать конкретной задачи; ничего не менять в коде/данных «по собственной инициативе».

## 4. Карта репозитория (2026-10-14)

| Путь | Что это |
|---|---|
| `antibiotic_calc.html.template` → `antibiotic_calc.html`, `sw.js`, `manifest.webmanifest`, `icons/`, `vendor/` | Офлайн single-page калькулятор доз (PWA). `antibiotic_calc.html` и штамп `sw.js` — **генерируются** `db/build_html.py`, руками не править. |
| `db/` | `build_db.py` (source gate → `antibio_db.json`), `validate_db.js` (0 errors обязательны), `build_html.py` (+ `--check`), `db_diff.py` + `CHANGELOG_DB.md` (любое изменение клинической БД — с записью в журнал; CI это требует), `diseases/` — исходные записи. |
| `server.js` | Статика оболочки по allowlist + loopback-only прокси `/v1`,`/v2` на движок. |
| `clinical_engine/` | Движок, API (`clinical_engine/api/app.py`, uvicorn :8000, loopback peer gate), review workbench (local-only), golden cases, тесты. Логика движка — frozen. |
| `src/pipeline/`, `src/llm/` | Извлечение из PDF КР: router (pymupdf → MinerU/docling), layout, semantic, LLM-экстракция, KB. `python -m src.pipeline.main --help`. |
| `medical_normalizer/`, `medical_dictionary/` | FROZEN нормализатор и его словари (source of truth для синонимов/ATC). |
| `dose_verification_sandbox/`, `tests/` | Песочница верификации доз RC030 и её архивные тесты (404). |
| `docs/audits/` | Аудиты 2026-10-14 (промпт, отчёт, отчёт об исправлениях). `docs/governance/` — конституция. `docs/history/` — архив отчётов/RCA/базлайнов (индекс в README). |
| Корень `*.md` | Живые документы: `HANDOFF.md`, `GOVERNANCE_SOURCE_OF_TRUTH.md`, `PROJECT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`, `AI_LOG.md`, `ROADMAP_STATUS.md`, политики/спецификации/RFC/контракты, на которые ссылается код. |

Текущие цифры (120 нозологий: 65 расчётных / 55 заблокировано, 47 препаратов, статусы источников) — в `PROJECT_STATE.md` и `GOVERNANCE_SOURCE_OF_TRUTH.md`, не здесь.

## 5. Команды

```
uv python install 3.12 && uv sync --frozen --extra clinical --extra tests   # requires-python ==3.12.*
python -m pytest -q                      # все testpaths (pyproject): 2026-10-14 → 2684 passed, 28 skipped
python -m pytest tests -q                # архив RC030: 404 passed
npm run validate                         # node db/validate_db.js — 0 errors обязательны
python db/build_db.py                    # пересборка БД (НЕ использовать --skip-source-gate: он снимает статусы гейта)
python db/build_html.py                  # html + штамп sw.js; `--check` — без записи, так же в CI и pre-commit
npm ci && npm run build:css              # Tailwind 3.4.17 CLI → vendor/app.css (статический CSS, H-1); обязателен после правки классов в template, затем build_html
python db/db_diff.py --git origin/main   # запись для CHANGELOG_DB.md при изменении db/antibio_db.json
ruff check .                             # E9 + полный pyflakes; FROZEN-модули только через per-file-ignores
npm start                                # node server.js → http://127.0.0.1:8080 (HOST=127.0.0.1)
uvicorn clinical_engine.api.app:app --port 8000   # движок отдельно; ENGINE_PROXY_ALLOW_LAN=1 — явное исключение владельца
```

Pipeline (на машине с корпусом; `ANTIBIO_CORPUS_DIR` переопределяет путь): проверить LLM-провайдер (`python main.py doctor`) → `python -m src.pipeline.main extract_raw` (resume-safe) → `validate` → `knowledge`; `python -m src.pipeline.prefilter --dry-run` при изменении `clinrecs.json`, `--restore` для отката.

CI (`.github/workflows/ci.yml`, `ubuntu-24.04`, Python 3.12 / Node 24): pytest + validate + `build_html.py --check` + гейт `CHANGELOG_DB.md`; `ruff`; `dependency audit` (pip-audit по ядру — блокирующий, ML-extras и `audit-site/` — отчёт); `gitleaks`. Красный core-audit чинится `uv lock --upgrade-package <name>`; принятие advisory — `--ignore-vuln <ID>` с письменным обоснованием.

## 6. Как продолжать типовые задачи

- **Исправление бага / доводка калькулятора:** golden-кейсы `clinical_engine/golden_cases/`, `test_calculator_*`; после правки шаблона — `python db/build_html.py`, затем `--check`; изменение БД — через `db/diseases/` + `build_db.py` + запись в `CHANGELOG_DB.md`.
- **Golden Case расходится с движком:** объяснить причину (ошибка движка / данных / кейса / неоднозначность КР), **не исправлять автоматически**.
- **Новая версия КР:** найти изменения и затронутые диагнозы, подготовить (не применить) обновление базы; применяет владелец.
- **Dictionary expansion:** `medical_dictionary/dictionary_candidates.json` (все `pending_review`), `dictionary_expansion.md`; никогда не auto-accept; принятые → `drug_synonyms.json` / `drug_atc.json`; затем `pytest medical_normalizer/tests -q`.
- **Parser improvement:** `quality_report.md` §14 (root cause); только добавление паттернов; тесты нормализатора зелёные; повторить quality audit.
- **Extraction improvement:** `PROJECT_STATE.md` (раздел LLM provider), `python main.py doctor`, `extract_raw` → `knowledge`; реальная валидация только на корпусе владельца.
- **Решения владельца-врача** (не инженерные; не принимать за него): очередь в `NEXT_TASK.md` п.1–3 — DOSA-записи `PENDING_OWNER_REVIEW`, `SOURCE_BASIS_MISSING`, записи «БЕЗ КР», `max_daily_mg` у детских мг/кг-схем, `db/schema.json`, `dose_unit`, пины ML-зависимостей, LICENSE, merge PR.

Перед коммитом всегда: `python -m pytest -q`, `npm run validate`, `python db/build_html.py --check`, `ruff check .` (после правки классов в template — ещё `npm run build:css`, его проверяет `test_tailwind_static_css`); затем протокол хендоффа (§3).
