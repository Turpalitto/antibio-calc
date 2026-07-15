# Golden Clinical Cases

> Milestone 12. Doctor-verified пары «вход → ожидаемый результат» для Clinical Decision Engine (spec §10.1 Tier 3).
> **Это инфраструктура. Сами клинические кейсы заполняет врач.**

## Что здесь

| Файл | Назначение |
|------|-----------|
| `schema.json` | JSON-schema формата кейса (инфраструктура) |
| `_TEMPLATE.json` | Пустой шаблон для нового кейса (инфраструктура) |
| `runner.py` | Раннер: загрузка → Engine → сравнение → PASS/FAIL |
| `<любой>.json` | **Реальные кейсы врача** (не начинаются с `_`) |

Раннер загружает все `*.json`, **кроме** начинающихся с `_` и `schema.json`.

## Как добавить кейс (врач)

1. Скопировать `_TEMPLATE.json` → `<id_кейса>.json`.
2. Заполнить `query` (диагноз/пациент/предпочтения) и `expect` (ожидания).
3. Оставить в `expect` только проверяемые поля, удалить остальные. Минимум одно.
4. Заполнить `provenance` (кто и когда верифицировал, источник).

**Изменение/добавление кейса требует врачебной проверки** (spec §10.1): кейс кодирует клиническую истину.

## Формат `expect` (все поля опциональны, проверяются только присутствующие)

| Поле | Проверяет |
|------|-----------|
| `first_drug_normalized` | препарат у `accepted[0]` (rank 1) |
| `first_drug_ref` | drug_ref у `accepted[0]` |
| `first_therapy_line` | линия терапии у `accepted[0]` |
| `first_route` | нормализованный route у `accepted[0]` (oral/iv/im/…) |
| `min_accepted` / `max_accepted` | число принятых рекомендаций |
| `accepted_empty` | принятых нет (true/false) |
| `excluded_drug_refs` | каждый указанный drug_ref есть в `excluded` |
| `not_accepted_drug_refs` | ни один не попал в `accepted` |
| `excluded_reason_contains` | подстрока в причине исключения |
| `engine_note_code` | код engine-note (напр. `NO_DIAGNOSIS_MATCH`) |
| `guideline_id` | выбранный guideline_id присутствует в accepted |
| `not_guideline_id` | указанный guideline_id НЕ присутствует в accepted (для negative exclusion proof) |
| `trace_code` | Decision code в traces (напр. `DIAGNOSIS_RESOLVED`) |
| `safety_flag_codes` | коды safety-флагов присутствуют (напр. `ALLERGY`) |
| `first_candidate_confidence_range` | `[min, max]` для confidence кандидата `accepted[0]` |

> `Recommendation.confidence` (§7.3) НЕ проверяется — это задокументированное неpopulated поле. Используется `candidate.confidence` (реальная confidence нормализатора).

## Как запустить

```
python -m clinical_engine.golden_cases.runner \
    --sqlite C:/clinrec_downloader/normalized_regimens.sqlite \
    --cases clinical_engine/golden_cases \
    --report golden_cases_report.md
```

По умолчанию используется production `diagnosis_index` (сейчас — AUTO_GENERATED_DRAFT). Для стабильных diagnosis-based кейсов сначала должна быть завершена врачебная курация индекса (Milestone 11).

## Примеры ожиданий из спецификации (§10.1) — как ориентир, НЕ готовые кейсы
- CAP взрослый, амбулаторно → `first_drug_normalized`/`first_therapy_line: "first"`/`first_route`.
- Доксициклин + беременность → `excluded_drug_refs: ["doxycycline"]`, `safety_flag_codes: ["PREGNANCY_CI"]`.
- Аллергия на пенициллины → `not_accepted_drug_refs` бета-лактамы, `excluded_reason_contains: "allergy"`.

## Проверка инфраструктуры (не клинические кейсы)
```
python -m pytest clinical_engine/tests/test_golden_runner.py -q
```
