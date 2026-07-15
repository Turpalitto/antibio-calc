# Physician Validation Guide — diagnosis_index

> Milestone 11. Как превратить `AUTO_GENERATED_DRAFT` в `PRODUCTION_CURATED`
> через явную врачебную проверку. **Система никогда не выбирает guideline сама.**

## Принципы (гарантируются инструментами)

- **Никакого авто-выбора.** Ни один конфликт не разрешается автоматически. Все стартуют как `pending_review`.
- **Каждый конфликт — отдельно.** Врач видит все guideline-варианты по каждому диагнозу и решает по одному.
- **Аудит-трейл.** Каждое решение фиксирует `decided_by`, `decided_at`, `rationale`.
- **Обратимость.** Ledger решений — редактируемый источник истины. Изменил решение → пересобрал. Черновик и ledger инструментом не перезаписываются.
- **Fail-safe статус.** `PRODUCTION_CURATED` присваивается ТОЛЬКО когда 0 pending и 0 невалидных решений. Иначе — `PARTIALLY_CURATED` (не для production).

## Артефакты

| Файл | Роль | Кто правит |
|------|------|-----------|
| `clinical_engine/resources/diagnosis_index.json` | Черновик (AUTO_GENERATED_DRAFT) | не трогать |
| `diagnosis_index_review.md` / `.json` | Отчёт по 101 конфликту (для чтения) | не трогать |
| `diagnosis_index_decisions.json` | **Ledger решений — врач редактирует его** | **ВРАЧ** |
| `clinical_engine/resources/diagnosis_index.curated.json` | Результат (derived) | генерируется |
| `diagnosis_index_curation_audit.json` | Аудит-трейл применённых решений | генерируется |

## Процесс

### 1. Сгенерировать ledger (все конфликты = pending)
```
python -m clinical_engine.tools.build_decision_ledger
```
Создаёт `diagnosis_index_decisions.json` — 101 запись, все `pending_review`.

### 2. Врач принимает решения — правит `diagnosis_index_decisions.json`
Для каждой записи в `decisions[]` установить `decision` (одно из словаря) + обязательно `decided_by`, `decided_at`, `rationale`:

| `decision` | Смысл | Доп. поля |
|-----------|-------|-----------|
| `pending_review` | не решено (по умолчанию) | — |
| `keep_all_complementary` | все guideline валидны/комплементарны — сохранить все | — |
| `select_primary` | выбрать один primary guideline | `chosen_guideline_id` |
| `duplicate_keep_one` | дубликат — оставить один | `chosen_guideline_id` |
| `split` | метка неоднозначна — переименовать по guideline | `renames: {guideline_id: новое_имя}` (покрыть ВСЕ guideline) |
| `remove_diagnosis` | строка диагноза некорректна — удалить | — |

Пример решённой записи:
```json
{
  "conflict_id": "c_...",
  "diagnosis": "Эпиглоттит",
  "decision": "select_primary",
  "chosen_guideline_id": "1832",
  "renames": null,
  "decided_by": "Иванов И.И., оториноларинголог",
  "decided_at": "2026-07-11T09:00:00Z",
  "rationale": "КР 1832 актуальнее и полнее (включает постинтубационный отёк)."
}
```
> Невалидные решения (без `decided_by`/`rationale`, или `chosen_guideline_id` не из вариантов, или `split` без всех guideline) **не применяются** и блокируют production.

### 3. Собрать курированный индекс
```
python -m clinical_engine.tools.build_curated_index
```
- Применяет ТОЛЬКО валидные врачебные решения.
- Пока есть pending/невалидные → статус `PARTIALLY_CURATED` (не для production).
- Когда все 101 решены и валидны → `PRODUCTION_CURATED` + `guideline_set_version: curated-<дата>`.
- Пишет аудит-трейл в `diagnosis_index_curation_audit.json`.

### 4. Отмена/правка (обратимость)
Изменить `decision` в ledger (в т.ч. обратно на `pending_review`) и повторить шаг 3. Результат детерминирован. Черновик не пострадает.

### 5. Развёртывание (отдельный шаг, после review)
Когда получен `PRODUCTION_CURATED`, движок переключается на курированный индекс через `EngineConfig(diagnosis_index_path=".../diagnosis_index.curated.json")` (или заменой файла). Это осознанный deploy-шаг, не автоматический.

## Что НЕ делает система
- Не предлагает «правильный» guideline.
- Не объединяет конфликты по эвристике.
- Не выявляет синонимы/опечатки (это отдельная врачебная задача — см. `diagnosis_index_review.md`).

## Проверка целостности инструментов
```
python -m pytest clinical_engine/tests/test_curation.py -q
```
