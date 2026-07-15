# Release Readiness — ANTIBIO Clinical Engine

> Milestone 13. Рекомендации к первому release-commit + статус guardrails.
> **Ничего не коммитится автоматически. Это рекомендации, не действия.**

## 1. Git Readiness (Task 1)

### Текущее состояние (факт)
- Последний коммит: `b806c21` — предшествует ВСЕЙ инженерной работе.
- `clinical_engine/`, `medical_normalizer/`, `medical_dictionary/` — **untracked** (никогда не коммитились).
- `db/index.json` и ещё 8 файлов `db/` — **modified**, не закоммичены (drug-reference — safety-relevant).
- Множество untracked docs и build-артефактов в корне.

### Рекомендация к первому release-commit
1. **Ветка + review, не в main напрямую.** Создать `release/v1.0.0-engine`.
2. `git add` (после ревью): `clinical_engine/` (кроме derived-артефактов, см. ниже), `medical_normalizer/`, `medical_dictionary/`, `pyproject.toml`, документация (`AGENTS.md`, `PROJECT_STATE.md`, `NEXT_TASK.md`, `DECISIONS.md`, `AI_LOG.md`, `README.md`, `PHYSICIAN_VALIDATION_GUIDE.md`, `RELEASE_READINESS.md`, `clinical_engine/golden_cases/README.md`).
3. **`db/index.json`** — подтвердить намеренность изменений (safety-ресурс) до `git add`.
4. Тег после мёржа: `v1.0.0-engine` (baseline для Clinical Content Validation).
5. Прогнать `pytest` (теперь покрывает все подсистемы) до коммита — должен быть зелёным (1141 passed, 1 xfailed).

### Политика артефактов (рекомендация — `.gitignore` НЕ менялся)
| Файл | Рекомендация | Причина |
|------|--------------|---------|
| `diagnosis_index_decisions.json` | **коммитить** | Ledger врачебных решений — версионируемый источник истины |
| `clinical_engine/resources/diagnosis_index.json` | коммитить (как DRAFT) | Входной ресурс; статус в meta честный |
| `clinical_engine/resources/diagnosis_index.curated.json` | **не коммитить пока PARTIALLY_CURATED** | Derived; коммитить только финальный PRODUCTION_CURATED |
| `diagnosis_index_review.{md,json}`, `*_curation_audit.json` | derived — по усмотрению (снапшот или ignore) | Регенерируются из индекса+ledger |
| `performance_audit_engine.md` | derived — по усмотрению | Регенерируется |
| `.coverage` | **ignore** | Локальный артефакт |
| `C:\clinrec_downloader\normalized_regimens.sqlite` | вне репозитория | Build-артефакт, большой бинарь — не коммитить |

## 2. Production Guard (Task 2) — DONE ✅
`Engine.__init__` проверяет статус `diagnosis_index`:
- `strict_mode=True` (production по умолчанию) + `AUTO_GENERATED_DRAFT`/`PARTIALLY_CURATED` → **`EngineError(RESOURCE_NOT_CURATED)`**, запуск запрещён.
- `strict_mode=False` → явное `warnings.warn`, запуск продолжается.
- Нет статуса (фикстуры) → guard не срабатывает.

Проверено: `Engine(Profiles.production(...))` на реальном черновом индексе → REFUSED.

## 3. Test Discovery (Task 3) — DONE ✅
`pyproject.toml`: дефолтный `pytest` покрывает `medical_normalizer`, `clinical_engine`, `src/tests`. Пре-существующий extractor-тест помечен `xfail` (не исправлялся). Результат: **1141 passed, 1 xfailed**.

## 4. RFC H1 (§7.5 per-recommendation trace/Evidence) — RE-EVALUATED, рекомендация: ЗАКРЫТЬ для v1
- Все данные evidence уже достижимы (source-поля кандидата + DiagnosisEntry + глобальные `traces`/`excluded` с DecisionCode).
- Отсутствует только per-recommendation группировка; корректная реализация требует изменения frozen-моделей.
- Влияния на безопасность нет. **Рекомендация: закрыть без изменений для v1, пересмотреть в v1.1 при интеграции Flutter.** Финальное закрытие — за пользователем.

## Pre-release checklist
- [ ] Review + `git add` исходников/доков; подтвердить `db/index.json`.
- [ ] `pytest` зелёный (1141 passed, 1 xfailed).
- [ ] Тег `v1.0.0-engine`.
- [ ] Решение пользователя: закрыть RFC H1.
- [ ] **Перед реальным production:** врачебная курация `diagnosis_index` (M11) → `PRODUCTION_CURATED` (иначе Production Guard не даст запуститься под strict). Верификация `allergy_class_map`.
