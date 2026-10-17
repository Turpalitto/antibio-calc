# ANTIBIO — Production Readiness Audit

**Дата аудита:** 2026-07-15  
**Режим:** READ → ANALYZE → VERIFY → REPORT  
**Репозиторий:** `C:\ANTIBIO`  
**Ветка / commit:** `main` / `b806c2127e1e3e87adea537e3ebea657b11f5ccc`  
**Решение:** **NOT PRODUCTION READY; P6 BLOCKED**

## 1. Executive summary

P4.4 создала физически целостный SQLite-артефакт с 31 336 Knowledge Objects и 100 854 provenance-записями; текущие проверки целостности не обнаружили объектов без provenance, битых ссылок или невалидного JSON. Производительность read-only Clinical Engine также достаточна для интерактивного применения: P95 около 10 мс на проверенном наборе из 736 диагнозов.

Однако репозиторий в целом не является Production Release Candidate. Основные блокеры: открытые секреты в исходном коде, фактически неверсионируемая основная кодовая база, невоспроизводимое окружение зависимостей, падение штатного тестового запуска, 0/7 Golden Cases на реальной БД, отсутствие врачебного approval, незавершённая P5.6 Review Workbench, несертифицированная полнота корпуса и дефект lineage/versioning в KB.

**Clinical Engine подключать нельзя. P6 начинать нельзя.** Замороженные Clinical Decision Engine, детерминированная медицинская логика, утверждённый клинический контент и bundle schemas изменять не требуется.

## 2. Проверенная архитектура и поток данных

Фактический основной поток:

```text
PDF corpus
  → PyMuPDF / MinerU fallback / Docling
  → DocLayout-YOLO / Table Transformer / RapidTable
  → Unified Document Model
  → Semantic entities
  → Knowledge Objects + provenance
  → kb_p44.db
  → regimen assembly
  → normalization / quality gates
  → ClinicalRegimen + TherapeuticOption (пока частично in-memory)
  → physician review (P5.6 отсутствует)
  → Clinical Engine (строго заблокирован draft-индексом)
```

Слои концептуально разделены правильно, но интеграционная граница P5.5 → P5.6 не завершена: 652 `TherapeuticOption` воспроизводятся в памяти, но не имеют production persistence и единой review queue.

## 3. Воспроизводимость репозитория

- Git root: `C:\ANTIBIO`.
- Remote: `https://github.com/Turpalitto/antibio-calc.git`.
- В Git отслеживается только **19 файлов**.
- `src/`, `clinical_engine/`, `medical_normalizer/`, большая часть документации, БД и production tooling находятся в untracked-состоянии.
- `git status --short` содержит более 200 записей.
- CI workflow и lock-файл зависимостей отсутствуют.
- Python 3.13 из текущего shell не содержит pytest; исторически рабочий runtime — Python 3.12.

Следствие: commit не способен воспроизвести проверенную систему на другой машине. Это production-блокер независимо от качества локального артефакта.

## 4. SQLite audit

### 4.1 `kb_p44.db`

| Метрика | Результат |
|---|---:|
| Размер | 55 476 224 bytes |
| `PRAGMA integrity_check` | PASS |
| Knowledge Objects | 31 336 |
| Provenance rows | 100 854 |
| Conflicts | 6 574 |
| Review rows | 6 574 |
| Объекты без provenance | 0 |
| Dangling provenance | 0 |
| Битые conflict/review references | 0 |
| Невалидный JSON | 0 |
| Точные дубли provenance | 0 |

Типы объектов: Dose 24 705; Medication 2 788; Evidence 2 190; Contraindication 841; Diagnosis 431; Recommendation 381.

Положительные свойства:

- обязательные поля действующего provenance-инварианта заполнены;
- table provenance присутствует в 466 строках для 104 PDF;
- нет объектов без источника;
- SQLite физически целостна.

Ограничения и дефекты:

- `paragraph` равен NULL во всех 100 854 строках;
- `bounding_box` отсутствует в 100 403 строках;
- table row/column/confidence отсутствуют в 100 388 строках;
- все 31 336 `relationships` пусты;
- 27 805 `history` пусты;
- `PRAGMA foreign_keys=OFF`;
- для `provenance.obj_id` и `provenance.guideline_id` нет индексов;
- состояния объектов дают 3 531 queued, тогда как таблица review содержит 6 574 записей — семантика счётчиков не едина.

### 4.2 Дефект version lineage

`KnowledgeBase._get_by_key()` выполняет поиск `content LIKE '%fragment%'` по сериализованному JSON. При совпадении создаётся следующая версия и supersede-цепочка, даже если совпадение является лишь общим текстовым фрагментом. В production DB обнаружены версии до **1986**, в частности для общего `Contraindication` «противопоказан».

Это не корректная история одного stable identity: ID вычисляется из content, а версия — из нечёткого совпадения другого content. Требуется отдельный RFC стабильного logical object key и явной lineage-модели.

### 4.3 Query benchmark

1000 прогретых read-only запросов:

| Запрос | Median | P95 | План |
|---|---:|---:|---|
| object by id | 0.0040 ms | 0.0043 ms | index |
| type + status | 1.2766 ms | 1.7501 ms | index |
| provenance by obj_id | 19.5766 ms | 25.2151 ms | full scan |
| provenance by guideline_id | 21.0006 ms | 27.1500 ms | full scan |

Добавление provenance-индексов даст наибольший безопасный прирост lookup-производительности, но должно выполняться после утверждения схемы и migration plan.

### 4.4 Regimen stores

`assembled_regimens.sqlite` физически целостна, содержит 2 675 записей, но отражает состояние до P5.4/P5.5: 1 543 REVIEW_REQUIRED и 1 132 REJECTED; реальных approvals нет. `TherapeuticOption` в этой БД отсутствуют.

Production normalized DB `C:\clinrec_downloader\normalized_regimens.sqlite`:

- 2 675 regimens;
- PASS 1 039, REVIEW 443, REJECT 1 193;
- approved: 0;
- reviewed_by: 0;
- manual_override: 0;
- 294 guidelines;
- source PDF/page/quote/guideline_id заполнены на 100%;
- dose заполнена у 1 921/2 675;
- route у 1 740/2 675;
- frequency у 1 969/2 675;
- duration_recommended у 1 316/2 675;
- ATC у 0/2 675.

## 5. Corpus audit

| Этап | Количество |
|---|---:|
| Source records в `knowledge_base.json` | 294 |
| Unique PDF names | 193 |
| Builder-selected production PDFs | 192 |
| Completed checkpoint PDFs | 192 |
| Per-PDF records в rebuild report | 192 |

Единственный PDF из этих 193, исключённый builder-правилами, находится в `archive_no_antibiotics` / `downloads_other`.

Но более широкий metadata index содержит **237 уникальных PDF**, отмеченных как содержащие антибиотики. С production selection пересекаются 179; ещё **58** antibiotic-flagged PDF не выбраны, из них 51 имеет хотя бы одну активную версию. Для этих 58 в репозитории нет формального manifest с индивидуальной причиной исключения.

Это не доказывает, что все 58 клинически релевантны: автоматический detector может давать false positive. Но это доказывает, что утверждение «192 PDF покрывают все антибиотик-содержащие рекомендации» не сертифицировано. Нужна отдельная corpus adjudication с reason code для каждого исключения.

## 6. Extraction и knowledge yield

Definitive P4.4 rebuild:

- 192 PDF;
- wall time 1 016.1 min (около 16.9 h);
- median 201.1 s/PDF;
- mean 310.54 s/PDF;
- P95 925.1 s/PDF;
- max 2 941.1 s/PDF;
- 7 719 tables;
- 188 529 cells;
- 101 842 semantic entities;
- 185 PDF с таблицами;
- 132 PDF с использованными table entities;
- 0 PDF с нулевым количеством entities;
- 0 PDF с нулевым KB yield.

Лог не содержит явных traceback/error завершения, но содержит 37 350 warning/error-like строк, в основном MuPDF syntax diagnostics. Это не доказывает потерю данных, но требует структурированного error budget вместо игнорирования шумного лога.

В router layout enrichment вызывается до quality decision и повторно на успешном return path. Это статически подтверждённый потенциально двойной тяжёлый layout-проход; эффект ещё не измерен сравнительным benchmark, поэтому улучшение производительности не заявляется.

## 7. Clinical data quality

Повторный clinical data audit:

| Категория | Количество |
|---|---:|
| Всего issues | 4 506 |
| DRUG_UNKNOWN | 1 166 |
| ROUTE_NOT_EXTRACTED | 902 |
| DOSE_NOT_EXTRACTED | 638 |
| DURATION_NOT_PARSED | 623 |
| FREQ_NOT_EXTRACTED | 613 |
| DUPLICATE_GUIDELINE_TITLE | 182 |
| DOSE_NOT_PARSED | 116 |
| FREQ_NOT_PARSED | 93 |
| EXTRACTION_GAP_CANDIDATE | 83 |
| DOSE_DAILY_MISREAD | 61 |
| DOSE_ALTERNATIVE_COLLAPSED | 29 |

Только guideline 1638 имеет зафиксированный PDF-confirmed ручной аудит. Репозиторий не содержит эталонного количества режимов для каждого из 294 guideline, поэтому автоматически доказать «сколько режимов есть в документе и сколько потеряно» для каждого guideline невозможно. Это обязательная задача врачебной валидации, а не основание придумывать completeness.

Из 2 675 normalized rows у 482 `drug_original` не найден простым нормализованным substring-сопоставлением в `source_quote`. Это эвристический сигнал, не доказанная медицинская ошибка; такие записи должны идти в review queue.

### 7.1 Клиническая семантика неизвестности

`pregnancy` моделируется как `bool | None`, но `renal_adjustment` — как `bool = False`. Если renal-признак не найден, parser устанавливает `False`, тем самым объединяя «источник явно говорит, что коррекция не требуется» и «данные отсутствуют». Для медицинской безопасности это потеря эпистемического состояния. Исправление требует изменения data contract/RFC и миграции, а не локального патча.

### 7.2 Coverage и invariants

Текущий coverage report: dose/route/contraindication/evidence — 100% по PDF-level definition; drug 97.9%; alternatives 58.3%; diagnosis 56.8%; first_line 28.6%; renal 24.0%; pregnancy 23.4%; duration/frequency/pediatric 0%.

Эти числа нельзя интерпретировать как полноту клинических полей. Например, invariant audit одновременно обнаруживает **8 412 Dose objects без unit**. Coverage означает наличие хотя бы одного объекта в документе, а не корректность каждого режима.

## 8. P5.4/P5.5 и готовность к врачебному review

Реальное воспроизведение pipeline в памяти:

- assembly: 2 675;
- до quality stage: PASS 566 / REVIEW 977 / REJECT 1 132;
- после quality stage: PASS 569 / REVIEW 987 / REJECT 1 119;
- quality examined: 935;
- route recovered: 72;
- ambiguous: 23;
- no match: 840;
- reject migration: A=627, B=25, C=444, D=23;
- создано 652 `TherapeuticOption`;
- осталось 467 unmigrated rejects;
- 652/652 options имеют complete provenance по действующей проверке;
- reviewable target: 1 556 `ClinicalRegimen` + 652 `TherapeuticOption` = 2 208.

`clinical_engine/review_workbench/` содержит только пустой `__init__.py`; production `ClinicalReviewTask`, priority scoring, lifecycle, permissions, dashboard API, metrics и требуемые 20+ тестов отсутствуют. Legacy script поддерживает только старый regimen workflow и не закрывает P5.6.

Следовательно, система ещё не готова к управляемой врачебной валидации двух типов объектов.

## 9. Clinical Engine и Golden Cases

Golden runner на реальной normalized DB:

- total: 7;
- PASS: 0;
- FAIL: 7;
- ERROR: 0.

Часть failures вызвана несовместимыми synthetic guideline IDs в Golden expectations и реальными numeric IDs. Allergy case также не подтвердил ожидаемые safety flags/exclusion. Это означает, что Golden suite сейчас не является валидным release gate и одновременно не подтверждает корректность Engine на production artifact.

Strict Engine guard правильно блокирует draft diagnosis index. `curated_knowledge.json` содержит 0 approved diagnoses, 0 approved regimens и 0 links; status `PARTIALLY_CURATED`. Diagnosis curation: 0/101 resolved. Regimen curation: 0/449 resolved.

Отдельный дефект: validator возвращает `CURATED_VALID` для полностью пустых списков из-за vacuous truth. Strict Engine пока блокируется другим guard, но такой false-green validator не должен участвовать в certification.

## 10. Performance audit

Read-only Engine audit по 736 diagnoses:

| Метрика | Adult | Heavy |
|---|---:|---:|
| P50 | 2.413 ms | 2.291 ms |
| P95 | 10.279 ms | 9.997 ms |
| P99 | 13.207 ms | 12.301 ms |
| Max | 27.429 ms | 17.268 ms |

- init: 41.9 ms;
- throughput: 295–314 queries/s;
- SQL mean 1.23/call, max 5;
- tracemalloc peak 2.3 MB;
- RSS около 30.2 MB;
- основной bottleneck: RegimenLoad, 68.4% времени.

Эти данные подтверждают техническую latency, но не медицинскую production readiness, потому что audit выполнялся с `strict_mode=False` на AUTO_GENERATED_DRAFT index.

## 11. Tests, static analysis и dependencies

### 11.1 Test execution

Штатный запуск:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider
```

падает на collection: `clinical_engine/tests/test_guideline_verifier.py` импортирует отсутствующий `clinical_engine.tools.verify_regimen_against_guideline`.

`pyproject.toml` не включает `clinical_engine/regimen/tests`, поэтому P5.3–P5.5 по умолчанию не входят в regression.

Диагностический запуск с исключением сломанного test module и явным добавлением regimen tests дал:

- 1 316 passed;
- 1 xfailed;
- 304 warnings;
- 419.09 s.

Source-only coverage этого неполного набора: **82%** (7 931 statements, 1 429 missed). Низкое покрытие сосредоточено в downloader/API/prefilter/extraction providers; результат не является release coverage, так как штатный suite не собирается.

### 11.2 Static analysis

Ruff обнаружил 207 нарушений, 109 auto-fixable. Среди исполняемых дефектов:

- undefined `ConformanceResult` в bundle loader;
- undefined `defaultdict` в layout;
- `checkpoint_t0` может использоваться до присваивания в pipeline main.

Mypy не начинает полноценный анализ из-за duplicate module identity: один router виден как `pipeline.extraction.router` и `src.pipeline.extraction.router`.

Обнаружены 22 функции с повышенной cyclomatic complexity; максимум среди критичных путей: semantic extraction 29, manifest validation 27, clinical audit 25, duration parser 24, router 23. В production paths остаются broad exceptions и silent `except/pass`.

### 11.3 Dependency integrity

`py -3.12 -m pip check` обнаруживает несовместимости и отсутствующие зависимости для doclayout-yolo, table-transformer, docling, MinerU и Ray. В частности, разные компоненты требуют несовместимые/отсутствующие Pillow, matplotlib, tqdm, packaging, seaborn и albumentations.

В layout и semantic source hardcoded пользовательский site-packages путь `C:\Users\TURPAL\...Python312\site-packages`. Это скрытая зависимость от одной рабочей станции.

## 12. Security audit

**Critical:** `src/pipeline/config.py` содержит два непустых API key в plaintext. Значения в отчёте намеренно не приводятся. Их необходимо считать скомпрометированными, отозвать/ротировать и заменить environment/secret-manager configuration. Проверка валидности ключей не выполнялась.

Дополнительные риски: subprocess path в OCR tooling, широкие exception handlers, отсутствие CI security gate и dependency lock. Доказательств exploitable SQL injection в проверенных внутренних query builders не получено; этот риск не завышается.

## 13. Documentation audit

Root governing documents и `docs/governance/*` противоречат друг другу:

- governance kernel/state всё ещё называют P4.4 активной;
- root `PROJECT_STATE.md` сообщает P4.4 certified и P5.3 implemented;
- root `NEXT_TASK.md` сообщает P5.5 completed и следующий этап physician review;
- HANDOFF, SESSION_SUMMARY, ARCHITECTURE_STATUS и DEVELOPMENT_BACKLOG содержат исторические состояния;
- root и docs-копии PROJECT_STATE/NEXT_TASK/DECISIONS/AGENTS/AI_LOG расходятся.

`PRODUCTION_SCORECARD.md` также устарел: security findings и текущие release blockers в нём отсутствуют. Документация не может использоваться как единый operational truth до синхронизации.

## 14. Реестр найденных проблем

| ID | Severity | Место / причина | Последствие | Требуемое действие | Сложность | Rebuild / migration / tests |
|---|---|---|---|---|---|---|
| PRA-001 | Critical | plaintext API keys в config | компрометация внешних сервисов | немедленная ротация, secrets policy | Low–Medium | tests: secret scan |
| PRA-002 | Critical | только 19 файлов tracked | система не воспроизводима из commit | нормализовать Git inventory и release branch | High | CI/tests обязательно |
| PRA-003 | Critical | штатный pytest падает на collection | отсутствует release regression | восстановить/удалить по RFC obsolete verifier contract | Medium | tests обязательно |
| PRA-004 | Critical | Golden 0/7 на real DB | клиническая корректность Engine не доказана | пересобрать Golden IDs/expectations по реальным источникам и врачебной валидации | High | revalidation + tests |
| PRA-005 | Critical | 0 physician approvals, draft indexes | unsafe CDS cutover | завершить P5.6 и double review/adjudication | High | persistence + tests |
| PRA-006 | High | P5.6 Review Workbench отсутствует | 2 208 объектов нельзя валидировать управляемо | реализовать утверждённый P5.6 scope | High | migration + 20+ tests |
| PRA-007 | High | 58 antibiotic-flagged PDF вне selection без reason codes | corpus completeness неизвестна | corpus manifest + clinical adjudication | Medium–High | возможно targeted extraction |
| PRA-008 | High | JSON `LIKE` определяет lineage; version до 1986 | ложные supersede/conflict chains | RFC logical identity + schema migration | High | KB rebuild + tests |
| PRA-009 | High | 8 412 Dose без unit | dose objects не клинически самодостаточны | review classification, parser/validator contract | High | targeted re-extraction/normalization |
| PRA-010 | High | 4 506 data quality issues | неполные/искажённые regimens | root-cause program по категориям | High | targeted reruns + revalidation |
| PRA-011 | High | dependency conflicts, нет lock | runtime не воспроизводим | поддерживаемая environment specification | High | installation smoke tests |
| PRA-012 | High | hardcoded user site-packages | работа только на конкретной машине | удалить после dependency packaging RFC | Medium | tests |
| PRA-013 | High | пустой curated validator даёт green | ложная certification | non-empty invariants | Low | regression tests |
| PRA-014 | High | undefined runtime names | возможные production crashes | исправить после code-freeze/RFC triage | Low | unit tests |
| PRA-015 | High | stale assembled store, options only in memory | P5.5 не имеет устойчивого handoff | unified review persistence | Medium–High | migration + integration tests |
| PRA-016 | High | renal unknown сводится к False | потеря медицинской неопределённости | tri-state data contract RFC | Medium–High | migration + clinical tests |
| PRA-017 | High | governing docs противоречат | неверный operational state | единая canonical doc hierarchy | Medium | doc consistency test |
| PRA-018 | Medium | provenance lookup full scan | 20–27 ms lookup, ухудшение при росте | индексы obj_id/guideline_id | Low | schema migration + benchmark |
| PRA-019 | Medium | возможный двойной layout call | лишняя длительная обработка | instrument before/after и устранить только после доказательства | Medium | targeted benchmark/tests |
| PRA-020 | Medium | 37 350 parser warnings | сигнал/ошибки не различимы | structured warning taxonomy/error budget | Medium | logging tests |
| PRA-021 | Medium | paragraph почти/полностью отсутствует, bbox sparse | неполная точная локализация | определить availability contract и coverage | Medium–High | возможно extraction rerun |
| PRA-022 | Medium | relationships пусты, history в основном пуст | platform graph/version goals не реализованы полностью | RFC relationships/lineage | High | migration/rebuild |
| PRA-023 | Medium | foreign keys OFF | целостность не enforced | schema evolution и FK tests | Medium | migration |
| PRA-024 | Medium | default pytest исключает regimen tests | ложный green regression | исправить test discovery | Low | tests |
| PRA-025 | Medium | 207 lint errors, broad exceptions, high complexity | maintenance и hidden failures | приоритетный quality backlog | Medium–High | targeted tests |
| PRA-026 | Medium | 8 age-group DB warnings | потенциально неверная population applicability | physician review исходных рекомендаций | Medium | revalidation |
| PRA-027 | Medium | ATC 0/2 675 | заявленная normalization неполна | определить обязательность и источник | Medium | normalization + tests |
| PRA-028 | Medium | review object counters расходятся | неоднозначная operational metric | формализовать review semantics | Medium | migration/tests |

## 15. Приоритет remediation

### Gate 0 — немедленная безопасность и воспроизводимость

1. Ротировать открытые API keys.
2. Зафиксировать полный production source inventory в Git без включения медицинских секретов/временных артефактов.
3. Создать locked Python 3.12 environment и CI smoke/regression pipeline.
4. Восстановить штатный test collection и включить regimen tests.

### Gate 1 — клиническая готовность к review

1. Реализовать P5.6 Review Workbench без подключения Clinical Engine.
2. Persist `ClinicalRegimen` и `TherapeuticOption` в единый append-only review/audit contract.
3. Выполнить минимум 20 lifecycle/permission/provenance/audit tests.
4. Провести double blinded physician review + adjudication 2 208 объектов.

### Gate 2 — data integrity

1. Сертифицировать corpus manifest, включая 58 спорных PDF.
2. Исправить lineage/versioning через отдельный RFC и одну миграцию.
3. Разобрать Dose-without-unit и 4 506 quality issues по root cause.
4. Исправить tri-state renal semantics и false-green curation validation.

### Gate 3 — release certification

1. Пересобрать/перевалидировать только затронутые слои по утверждённым migration plans.
2. Создать real-ID Golden Dataset, подтверждённый источниками и врачами.
3. Повторить полный regression, corpus audit, performance benchmark и independent audit.
4. Только после всех PASS рассматривать P6.

## 16. Что даст максимальный эффект

- **Качество:** единый Git/dependency/CI baseline и P5.6 review lifecycle.
- **Производительность:** сначала устранение доказанного двойного layout прохода (после before/after измерения), затем provenance indexes.
- **Точность рекомендаций:** врачебная валидация 2 208 объектов, targeted review 4 506 quality findings и corpus adjudication 58 PDF.
- **Надёжность:** исправление KB logical identity/version lineage, non-empty certification invariants и real production Golden suite.

## 17. Что можно оставить как есть

- Существующий canonical provenance mapping P4.4, пока новые проверки не докажут дефект.
- Физически целостный `kb_p44.db` как audit/reference artifact; не объявлять его окончательным authoritative clinical store.
- Архитектурное разделение `ClinicalRegimen` и `TherapeuticOption`.
- Strict guard Clinical Engine, блокирующий draft data.
- Текущую latency Engine как performance baseline, но не как clinical certification.

## 18. Что не следует менять

- Clinical Decision Engine logic.
- Детерминированную медицинскую recommendation logic.
- Утверждённый медицинский контент и frozen medical data.
- Frozen bundle schemas.
- P5.3/P5.5 архитектурное разделение типов без отдельного RFC.

## 19. Какие операции потребуются

| Операция | Требуется | Область |
|---|---|---|
| Полная пересборка SQLite | Да, но только после lineage/review schema RFC | KB + review persistence |
| Повторная extraction | Targeted, не blanket | 58 corpus candidates, 83 extraction-gap candidates, доказанные parser gaps |
| Повторная normalization | Да, после исправления контрактов | dose/frequency/duration/renal/ATC категории |
| Повторная клиническая валидация | Да | 2 208 reviewable objects + спорные corpus/data findings |
| Новые тесты | Да | collection, Golden, P5.6, lineage, corpus, empty curation, dependencies, secrets |

## 20. Оценка по 10-балльной шкале

Шкала: 0–2 — отсутствует/небезопасно; 3–4 — прототип/блокирующие дефекты; 5–6 — рабочая инженерная система без production certification; 7–8 — production candidate с ограниченными рисками; 9–10 — независимо сертифицированная production-система.

| Категория | Оценка | Обоснование |
|---|---:|---|
| Архитектура | 6.0 | Слои и provenance contract сильны; P5.6 handoff и KB lineage не завершены |
| Качество кода | 4.5 | Большой test corpus, но runtime undefined names, broad exceptions, lint/typing blockers |
| Клиническая база | 4.0 | Хорошая traceability, но 0 approvals, 4 506 issues и неизвестная corpus completeness |
| SQLite | 6.0 | Физическая целостность высокая; lineage, индексы, FK и review persistence требуют работы |
| Производительность | 6.5 | Engine latency хорошая; rebuild 16.9 h и layout duplication требуют измеренной оптимизации |
| Тестирование | 4.5 | 1 316 диагностически passing, но штатный suite падает и Golden 0/7 |
| Security | 2.0 | Открытые API keys и отсутствие security/CI gate |
| Документация | 4.0 | Документов много, но governing state противоречив и scorecard устарел |
| Production readiness | 3.0 | Несколько независимых critical gates остаются открытыми |

**Итоговая объективная оценка проекта: 4.4/10.**

Это не оценка идеи или объёма выполненной работы. Она отражает текущую способность другой инженерной команды получить commit, воспроизвести систему, прогнать release gates и безопасно использовать клинический результат. Сегодня это невозможно без локальной машины, untracked source, ручных знаний и незавершённой врачебной валидации.

## 21. Final decision

### P4.4

Физический rebuild завершён и базовые provenance/integrity gates сильны. Но platform-wide certification P4.4 нельзя считать окончательной, пока не исправлен logical identity/version lineage и не сертифицирован corpus manifest. Существующий артефакт можно сохранить как проверенный baseline.

### P5.6

**Не реализована.** Это правильный следующий milestone: Review Workbench для `ClinicalRegimen` и `TherapeuticOption`, без подключения Clinical Engine.

### P6

**NOT READY / BLOCKED.** Минимальные условия разблокировки: воспроизводимый репозиторий и runtime, зелёный штатный regression, P5.6, врачебный review/adjudication, real Golden PASS, corpus certification и отсутствие Critical/High safety gates.

## 22. Воспроизводимость аудита

Основные реально выполненные проверки:

- `git status`, `git ls-files`, branch/commit/remote discovery;
- read-only immutable SQLite integrity/schema/content queries;
- `py -3.12 -m pytest` штатный и диагностический runs;
- source-only coverage диагностического набора;
- Ruff, Mypy startup, complexity/AST inventory;
- `py -3.12 -m pip check`;
- Golden runner на production normalized SQLite;
- Engine performance audit по 736 diagnoses;
- P5.4/P5.5 in-memory reproduction;
- invariant, clinical data, corpus selection и query-plan audits;
- статическая сверка pipeline, contracts, docs и security configuration.

Никакие медицинские данные, Clinical Engine logic, bundle schemas или SQLite-артефакты в ходе аудита не изменялись. Аудит не заявляет медицинскую корректность там, где отсутствует врачебный ground truth.
