# Отчёт об исправлениях по аудиту 2026-10-14

Основание: `AUDIT_2026-10-14.md` (27 находок, HEAD `1885894`). Ветка:
`arena/2013101a-antibio-calc`. Среда: Python 3.11 venv из `uv.lock`
(3.12 в песочнице недоступен — см. `AI_LOG.md`), Node 22. CI проверяет на 3.12 / Node 24.

## Итог проверки

| Проверка | До | После |
|---|---|---|
| `python -m pytest -q` (testpaths) | 2526 passed / **1 failed** / 30 skipped | **2660 passed / 0 failed / 30 skipped** |
| `pytest tests` (архив RC030) | 402 passed / **2 failed** | **404 passed** / 3 skipped |
| `npm run validate` | 0 errors (правил почти не было) | 0 errors / 518 warnings (все в заблокированных записях или «owner review») |
| Расчётных / заблокированных записей | 115 / 4 (+1 без ключа; 48 машинных считались как «КР») | **65 / 55** |
| Сборка | детерминирована | детерминирована: db `56727a27f050…`, html `3e8b5af9d4e7…` (765 620 B), sw `build-ff813dcc5750` |
| `ruff --select F821` | 6 | 0 |
| `ruff check .` (раунд 3: полный pyflakes `F` + `E9`) | ~200 F401/F541/F811/F841 | **0** (FROZEN `medical_normalizer/` исключён из стилевых правил, не правился) |
| GitHub Actions CI после раунда 3 | — | **✅ runs 38570533400 / 38571378607** (ruff при полном `F`, шаг changelog-gate, pytest 2675, пересобранный html) |
| GitHub Actions CI | 4/4 красных прогона, никогда не был зелёным | **✅ run 38563366043** (PR #1: pytest + validate на 3.12/Node 24, secret scan) |
| jsdom end-to-end smoke собранной оболочки | — | пройден (возраст/беременность/СКФ, блокировки, «БЕЗ КР», МИС-текст) |

## Статус находок

| ID | Сев. | Статус | Что сделано | Где проверено |
|---|---|---|---|---|
| B-1 | CRIT | ✅ | 48 DOSA-записей `calculation_blocked: true`; дефекты маппера исправлены (`каждые N ч`, `г`→мг, per-dose); без регенерации | `test_dosa_to_db_mapper.py` (+14), `test_calculator_source_gate.py`, `test_build_db.py` |
| B-2 | CRIT | ✅ | три уровня основания: КР / `NO_FEDERAL_CR_EXPERT_BASIS` («БЕЗ КР», расчётные, 32) / `SOURCE_BASIS_MISSING` (блок, 3); `--block-no-cr` | гейт-тесты, harness `test_disease_source_label_never_invents_a_federal_guideline` |
| A-2 | HIGH | ✅ | фикстура PDF ужимает текст под ширину колонки | `test_regimen_candidates.py` 33 passed на DejaVu |
| C-1 | HIGH | ✅ | `server.js`: прокси только для loopback-пиров, XFF, лимит тела | `src/tests/test_static_server_policy.py` (23) |
| C-2 | HIGH | ✅ | `/v1/recommend`: peer-гейт (XFF-aware) + 413 на v1/v2 | `clinical_engine/tests/test_api_peer_policy.py` (8) |
| B-3 | HIGH | ✅ / ⏳ | `validate_db.js` — исполняемая схема с правилами правдоподобия; `db/schema.json` **не трогался** (AGENTS.md «без обсуждения») — решение владельца | `src/tests/test_validate_db_rules.py` (33) |
| B-4 | HIGH | ✅ | статусы и бейджи различают КР / без КР / заблокировано; шапка «65 расчётных, 55 закрыто» | harness `test_source_banner_wording_per_status`, `test_header_stats_…` |
| B-5 | HIGH | ✅ | `age_restriction_min` в метаданных + флаг по возрасту пациента | harness `test_age_restriction_flag_matrix`, smoke (цефиксим 3 мес, доксициклин 5 лет) |
| F-1 | HIGH | ✅ | README/AGENTS/GOVERNANCE/PROJECT_STATE/NEXT_TASK/DECISIONS/AI_LOG обновлены фактами | — |
| A-1 | MED | ◐ | раздел Setup (uv + 3.12) в README; `requires-python` не ослаблялся | — |
| A-3 | MED | ✅ | `src/pipeline/main.py` сам выставляет `sys.path` как pytest; работают `-m src.pipeline.main`, путь к скрипту, `cd src/pipeline` | ручной прогон 4 вариантов, `src/tests` 501 passed |
| E-1 | MED | ✅ | POSIX-пути в манифестах `generated/`, генераторы `as_posix()`, потребители терпят `\\` | `pytest tests` 404 passed |
| E-2 | MED | ⏳ | fixture-корпус — backlog | — |
| E-3 | MED | ✅ | golden-кейсы (11 схем × вес → мг/мл/таб/капс/флакон) | `test_calculator_dose_golden.py` (23; негативная проверка 3/3) |
| E-4 | MED | ✅ | `TYPE_CHECKING`-импорты, `pytest`/`Path` в тесте | `ruff --select F821` = 0 |
| D-1 | MED | ✅ | раунд 3: 156 авто-исправлений F401/F541/F811 вне FROZEN `medical_normalizer/`, F841 вручную в pipeline, `select = ["E9", "F"]` + документированные `per-file-ignores` (FROZEN — только стилевые правила, тесты/legacy — F841) | `ruff check .` clean при полном pyflakes; pytest 2671/30 |
| D-2 | MED | ✅ | раунд 3: 5 «тихих» `except Exception: pass/continue` в `src/pipeline` (OCR-fallback, salvage JSON LLM, resume-фильтр `extraction_raw.json`, счётчик схем в отчёте, кэш извлечения) теперь логируют причину; поведение не менялось. `layout.py` (ML-таблицы без локального покрытия) и `config.py` (возврат `None` по контракту) оставлены | `src/tests` 501/13 |
| D-3 | MED | ✅ | `db/build_db.ps1` — тонкая обёртка над `build_db.py` | — |
| C-3 | MED | ✅ | allowlist файлов вместо расширений | `test_static_server_policy.py` |
| C-4 | MED | ⏳ | CVE extras / `npm audit` — backlog | — |
| B-6 | MED | ⏳ | `dose_unit` на уровне схемы — решение владельца; валидатор уже имеет лимиты по единицам | — |
| B-7 | MED | ✅ | `concentration_mg_per_ml` тобрамицин/нетилмицин; правило `route≠[]` (29 пустых — все в заблокированных); `calculation_blocked` всегда явный | `test_validate_db_rules.py` |
| B-8 | MED | ✅ | капсулы — целые, с фактической дозой | harness `test_format_tablets_never_splits_a_capsule…` |
| F-2 | MED | ⏳ | AGENTS.md ≤ 200 строк — backlog | — |
| F-3 | MED | ⏳ | `audit-site/` — backlog | — |
| H-1 | MED | ⏳ | статический Tailwind — backlog | — |
| H-2 | MED | ✅ | `CACHE_VERSION` генерируется `build_html.py`; тест на устаревшее значение | `test_build_reproducibility.py` (+4) |
| G-1 | LOW | ⏳ | архив корня — backlog | — |
| G-2 | LOW | ✅ | `.gitignore` += `node_modules/`, `.npmrc` | `git check-ignore` |
| G-3 | LOW | ✅ | домашние пути/e-mail удалены из 6 документов и docstring | `grep` |
| A-4 | LOW | ✅ | `ubuntu-24.04`, actions на Node 24 (`setup-uv` по SHA) | CI run 38569123307 — 3 джоба ✓, аннотаций о Node 20 / ubuntu-latest нет |
| H-3 | LOW | ✅ | `favicon.ico` 16/32/48, `<link rel="icon">`, отдаётся app.py/server.js, в precache | `test_favicon_is_served…` |
| G-4, G-5, D-4 | LOW | ⏳ | backlog (`NEXT_TASK.md`); G-5 — документированный дефолт с override `ANTIBIO_CORPUS_DIR` | — |
| I-1 | INFO | ✅ | возраст пациента (д/нед/мес/лет) → группа + проверка порогов | harness `test_age_parsing_and_group_boundaries` |
| I-2 | INFO | ✅ | СКФ как вход, флаг по `renal_adjustment` | harness `test_pregnancy_and_renal_flags` |
| I-3 | INFO | ✅ | беременность/лактация как вход, «Противопоказан» → красный | harness, smoke (доксициклин) |
| I-4 | INFO | ◐ | раунд 3: таблицы не объединены (движок не подключён, слияние — решение владельца), но закреплены тестом: все расчётные препараты БД есть в `DRUG_CLASSES` оболочки и в `allergy_class_hierarchy` движка; членство в β-лактамах совпадает; 3 противотуберкулёзных (изониазид, этамбутол, пиразинамид) добавлены в `DRUG_CLASSES` как `antituberculous` (поведение не изменилось). 6 препаратов только из заблокированных записей отсутствуют в таблице движка — зафиксированы как долг владельца | `test_allergy_class_consistency.py` (4) |
| I-5 | INFO | ✅ | golden-кейсы как данные + прогон в CI | `golden/calculator_dose_golden.json` |
| I-6, I-7 | INFO | ✅ | `db/db_diff.py` + `CHANGELOG_DB.md`; `.pre-commit-config.yaml` + `build_html.py --check` (и шаг CI). Раунд 3: шаг CI «Clinical DB change requires a CHANGELOG_DB.md entry» — PR с изменённым `db/antibio_db.json` без правки `CHANGELOG_DB.md` падает и печатает `db_diff.py --git origin/<base>` | `test_db_diff.py` (7), `test_build_reproducibility.py` (15) |

Легенда: ✅ закрыто, ◐ частично, ⏳ в backlog (`NEXT_TASK.md`, раздел 2026-10-14).

## Что требует решения владельца-врача (не инженерные задачи)

1. 50 заблокированных DOSA-записей: регенерация маппером в карантин и построчный ревью.
2. 3 записи `SOURCE_BASIS_MISSING` (erysipelas, pneumococcal_meningitis, brucellosis): нужен `cr_id` или документированный `cr_note`.
3. 32 записи «БЕЗ КР»: подтвердить основание или собирать с `--block-no-cr`.
4. 4 детских мг/кг-режима без `max_daily_mg` (aom_child амоксиклав, ut_child цефотаксим, дифтерия бензилпенициллин, коклюш азитромицин).
5. Судьба `db/schema.json` (регенерировать из правил валидатора или удалить).
