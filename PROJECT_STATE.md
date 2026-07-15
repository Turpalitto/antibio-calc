# PROJECT STATE — ANTIBIO (antibio-calc + pipeline)

## 2026-07-15: Review Governance Hardening (GOV-001/002/003 FIXED)

Repository recovery is complete (commit `32096af`, fresh clone validated). Physician pilot
activation found three governance defects before any real reviewer was registered: (1) no
reviewer-registry enforcement in `ReviewService`, (2) Reviewer B could see Reviewer A's verdict
before submitting, (3) two-reviewer consensus alone reported `PHYSICIAN_APPROVED` with no Medical
QA Lead gate. All three are now fixed — see `ROOT_CAUSE_REGISTER.md` (GOV-001/002/003),
`P56_REVIEW_GOVERNANCE_HARDENING_REPORT.md`, `REVIEWER_IDENTITY_AND_ASSIGNMENT_POLICY.md`,
`SECOND_REVIEW_BLINDING_SPEC.md`, `REVIEW_CONSENSUS_STATE_MODEL.md`, `MEDICAL_QA_SIGNOFF_SPEC.md`.
Reviewer registry exists but is intentionally **empty** — `pilot_status = WAITING_FOR_REVIEWERS`.
No real reviewer has been registered, no real clinical decision exists, approved-object count
remains 0 (verified against all 9,153 tasks, not just the 30-task pilot). Clinical Engine remains
disconnected. P6 remains BLOCKED.

## Current authoritative state — 2026-07-15

P5.6 stage: **ACCEPTANCE / NOT COMPLETE**. Review Workbench validated on 1,556 ClinicalRegimen + 652 TherapeuticOption candidates; total queue 9,153, all PENDING, approved=0. Canonical pytest 1,373 collected / 1,371 PASS / 0 FAIL. P6 remains BLOCKED; Clinical Engine disconnected.

Blocking owner actions: credential rotation/revocation; recover canonical source into Git and reproduce from fresh clone. See `GOVERNANCE_SOURCE_OF_TRUTH.md` and `P5.6_PRODUCTION_RECOVERY_REPORT.md`. Historical content below retained.

**2026-07-14: ROLE CHANGE.** Agent role is now defined by `ANTIBIO_PROJECT_CONSTITUTION.md`
(Production Architecture Lead + Senior Implementation Engineer + Medical Software QA + Production
Auditor). AGENTS.md §0.1 "Reviewer-only" is superseded/historical. Frozen scope (Clinical Engine,
medical content, bundle schemas, validated data) unchanged. See constitution §3 for exact frozen
list and §6 for the Definition of Done now required to close any milestone, including the
already-claimed-but-unverified P4.4.

**P5.3 (2026-07-15): Clinical Regimen Assembly Engine IMPLEMENTED** (additive `clinical_engine/
regimen/` package). Sources regimen structure from `normalized_regimens`, enriches from kb_p44 on
deterministic guideline_id linkage (`P5.3_DECISION_RECORD.md`). Measured: 2,675 regimens, 100%
explainable-to-source-line, enrichment coverage 81.6%, 5,615 conflicts (all UNRESOLVED), 0 shadow
divergence vs normalized_regimens (non-breaking), 14 tests pass. Engine NOT switched (shadow only).
Open: RC-023 (kb_p44 atomic linkage), RC-024 (reject-rate governance). See
`P5.3_IMPLEMENTATION_REPORT.md`. Next: RC-024 decision + approval-workflow population before P6.

---

**RESOLVED 2026-07-15.** The open discrepancy below is closed: P4.4 was rebuilt clean on the full
192-PDF corpus (checkpoint 192/192, 0 tracebacks) on a pipeline that also fixed PR-001 (table-loss)
and the full provenance contract (RC-012…018). Full audit executed on the finished KB: 0 blocking
invariant violations (INV-09 was 1,442 violations pre-fix, now 0), 0 silent nulls across 100,854
provenance rows, regression 72 passed/0 failed, CKY + Coverage baselines established. **P4.4
Production Knowledge Base is CERTIFIED** — see `PRODUCTION_SCORECARD.md` and
`PROVENANCE_CERTIFICATION.md` for the full evidence trail, and `P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md`
for regenerated real numbers (31,336 objects, not the stale 116/204 previously claimed).
**Scope caveat:** certification covers the KB build; it does NOT mean the Clinical Decision Engine
serves recommendations from this KB yet (RC-019, `ENTERPRISE_ARCHITECTURE_REVIEW.md` — P5/P6 scope).

*(Prior open-discrepancy text, preserved for history):* ROADMAP.md said P4.4 "✅ COMPLETE (real
exec)"; this section said P4.4 "ACTIVE + IN PROGRESS"; `p44_kb_checkpoint.json` showed only 2/193
corpus PDFs processed. Resolved above by real full-corpus execution + audit re-derivation.

**Версия:** 1.0.2-clinical-engine-perf-audited
**База:** КР МЗ РФ (cr.minzdrav.gov.ru)
**Статус:** Clinical Decision Engine — реализация завершена (M1-8) + аудит устранён (M9) + **Performance Audit пройден на реальных 2675 схемах, все цели §9.1 выполнены** ✅. `Engine.recommend()` — полный pipeline из 10 стадий.
**Базовая документация (принята 2026-07-10):** `ARCHITECTURE_V3.md` + `ENGINEERING_MASTER_PLAN.md` + `DEVELOPMENT_BACKLOG.md` — официальный план проекта. Design-фаза закрыта; изменения архитектуры — только по реальной инженерной причине (RFC).

**Фаза:** P1 Terminology Binding — Clinical Product Focus.

**P0 Status:** OFFICIALLY COMPLETE + FROZEN. See P0_COMPLETION_REPORT.md. Infrastructure locked.

**Process phase complete.** No more new rules. Focus: clinical product. Physician value, real cases, Golden validation.

**P1 Status:** P1-A COMPLETE + FROZEN. P1-B CLOSED (ACCEPTED + FROZEN). Genuine PASS after independent repro of 4 findings + minimal additive fixes only. P0 fixture pure. P1 dedicated. 0 failed. Golden PASS. No P1-A reg. Negative Golden now assert both guideline_id (present) and not_guideline_id (absent) to fully prove incorrect guideline exclusion.

**P2 Status:** P2-1 Conformance Validator — COMPLETE + FROZEN. Golden now proves incorrect guideline exclusion (not_guideline_id + trace_code). All audit medical findings addressed in data scope.

**P3 Status:** Clinical Data Curation — ACTIVE. Medical content only. Resolve 101 diagnosis conflicts, expand synonyms (incl. peds), structure renal, fill ATC, build 300+ Golden Cases. Target: PRODUCTION_CURATED. No engine changes.

**P4 Status (2026-07-13):** P4 — Document Intelligence Platform ✅ COMPLETE + Production Ready

P4.1 Multi-Engine Extraction ✅
P4.2 Layout Intelligence ✅ (P4.5 PRODUCTION RELEASE COMPLETE)
P4.3 Medical Semantic Layer ✅

**P4.5 FINAL CLINICAL ACCEPTANCE AUDIT (2026-07-13):** STRICT AUDIT COMPLETE — **A) P4.5 PASSED**.

- Full 12-step production audit executed (real corpus, reprocessor on 193 contributing PDFs, clinical field extraction measured via cells, before/after vs table_dependency_audit baseline, completeness table, table impact quantified, 0 FPs).
- Representative: 20 structured_tables on table-heavy PDF (dose/alt/ped/dur signals recovered from cells); 0 on non-table (correct).
- Reprocessor validated (checkpoint, resume, metrics: tables/cells/dose_cells/table_used/layout_processed).
- Regression: extraction/layout/semantic suites 11 passed (no regression).
- Engineering audit: code/arch/docs/benchmarks/clinical/consistent — PASS.
- **P4.4 Production Knowledge Base Platform — ✅ CERTIFIED 2026-07-15 (STRICT, real exec).**
  - Enhanced immutable KnowledgeObject + rich Provenance v2 (layout_engine, table_row/col/bbox,
    table_conf, original_text/normalized_value, guideline_id, schema_version) — canonical contract
    per `PROVENANCE_SPECIFICATION.md`.
  - `build_p44_kb.py` (production rebuild tool) + `kb_p44.db`.
  - Real measured (final, 192/192 corpus): **31,336 objects** (Dose 24,705, Medication 2,788,
    Evidence 2,190, Contraindication 841, Recommendation 381, Diagnosis 431); 100,854 provenance
    rows, 0 blocking invariant violations, 0 silent nulls.
  - Comprehensive reports: `P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md`, `PRODUCTION_SCORECARD.md`,
    `PROVENANCE_CERTIFICATION.md`.
  - **Next milestone (P5)** must resolve RC-019 (engine reads a different DB) as a first-class
    deliverable — see `ANTIBIO_ROADMAP_P5_P10.md`, `docs/rfc/P5_KNOWLEDGE_PLATFORM_RFC.md`.
  - See build_p44_kb.py, src/pipeline/knowledge_base.py.

See P4.5_PRODUCTION_AUDIT.md and table_dependency_audit.

All verified real (mechanics):
- 10/10 tests
- Router/Cache/Provenance/Semantic/Normalization/Knowledge Objects/Consistency
- Real PDFs (300+ ents, fallback paths)
- No raw text downstream

**TABLE DEPENDENCY AUDIT (2026-07-13, STRICT):** 963 PDFs corpus, 193 → 2675 regimens analyzed. 8-14% regimens + 13.6% stratified dosing + 55.9% peds facts table-origin (PyMuPDF verified + heuristics on source_quote/section). Critical dose/dur/alt loss measurable (real sepsis 4-col table → partial KB). **Verdict: P4.5 Layout before P4.4 data freeze.** See table_dependency_audit_2026-07-13.md + AI_LOG + DECISIONS.

**Next:** P4.5 Layout Intelligence productionization (enable full table extraction fidelity) **then** P4.4 content production / freeze on improved data. Mechanics of P4.4 complete; authoritative KB population gated per audit measurements. See ROADMAP + audit.

Big release strategy + paired validation rule active.

No Clinical Engine / bundle changes. Frozen preserved.

**Regimen Review Workbench (2026-07-11):** refined as physician-review tooling only. Default mode is read-only against upstream corpus and writes only `.md`/`.csv` artifacts; `regimen_review_ledger.json` updates require explicit `--update-ledger`. Target-area matching config moved to `clinical_engine/resources/regimen_review_areas.json`; deterministic confidence/match_reason/needs_manual_review/priority emitted. Rows sort by area → priority → diagnosis → regimen_id. Dry run: queue 438 → 305, 138 false positives excluded. Full tests: `python -m pytest -q` → 1266 passed, 1 xfailed, 1 warning.

**Frozen Components**
- Architecture v3
- BundleManifest + schema + validator
- Provider Ports + adapters
- Bundle Loader + wrapping
- Engine invariants
- Medical Normalizer
- SQLite schema
- Medical Dictionary
- Clinical Traceability Rule
- Optimization Rule
- P1-A Drug Terminology (TerminologyProvider)

**Current Milestone**
P2-1 Conformance Validator (Phase 2 Eval & Assurance)

**Active Issue**
P2-1 CLOSED (additive complete, frozen per workflow)

**Workflow Stage**
P2-1 full workflow complete: Analysis (enhanced) → RFC (light) → Impl (additive) → Tests (real 298 passed) → Review (PASS) → Freeze → Docs. Next: handoff + next item ANALYSIS ONLY.

**Current Test Status**
- Extraction/layout/router/semantic/document: **11 passed** (latest run).
- Reprocessor validated on real PDF (layout_processed, metrics collected).
- P4.5: representative + mechanism complete (20 tables on table-heavy PDF; 192 PDFs supported).

**Next Implementation Step**
P2-1 CLOSED. P2-2 Analysis ONLY (doc). STOP. No impl.

**Permanent laws:**
- Clinical value primary.
- Clinical Evidence Rule.
- Clinical Traceability Rule (law): 7 questions per rec. No black box.
- Optimization Rule (permanent): Never optimize infrastructure unless it directly improves clinical decision quality, safety, maintainability, or measurable performance.

If no measurable benefit exists, do not change it.

**DoD P1+:** Clinical Justification + Acceptance Criteria + traceability. Demonstrate physician benefit. No pure infra justification. No unmeasured opts.

**Текущий статус (2026-07-10):**
- P0-1 BundleManifest — **CLOSED + FROZEN**.
- P0-2 Provider Ports — **CLOSED + FROZEN**.
- P0-3 Bundle Loader — **CLOSED + FROZEN**.
- P0-4 Bundle Wrapping — **COMPLETE** (checklist migration).
- Все компоненты P0 заморожены. Изменения только по новому RFC.
- BundleManifest, JSON Schema, validator, Providers, Loader, Wrapping — **ЗАМОРОЖЕНЫ**.
- Введено постоянное правило проекта (ANTIBIO Development Workflow):

  1. Analysis (понять текущую реализацию, без кода)
  2. RFC / Design (только если требуется; лёгкий impl RFC, без редизайна архитектуры)
  3. Review (проверить assumptions)
  4. Implementation (инкрементально, additive, feature-flagged, без изменения поведения без approval)
  5. Tests (positive, negative, regression)
  6. Acceptance Review (DoD, RFC compliance, no feature creep)
  7. Freeze (контракты при завершении)
  8. Documentation (обновить все handoff docs, consistency audit, cross-IDE handoff)
  9. Close Issue

  Правило зафиксировано в DECISIONS.md, HANDOFF.md, AI_LOG.md. Репозиторий — единственный источник истины. AI Memory Rule: предполагать нулевую память в каждой новой сессии.

**P0 Status:** COMPLETE + FROZEN. See P0_COMPLETION_REPORT.md.

**Current Active:** P1 — Terminology Binding (per ENGINEERING_MASTER_PLAN). Analysis phase.

**P0-2 Provider Ports (2026-07-10):** CLOSED (frozen).

**P0-3 Bundle Loader (2026-07-10):** CLOSED + FROZEN. Pure generic loader.

**P0 COMPLETE (2026-07-10):** See P0_COMPLETION_REPORT.md + P0_Phase_Gate_Review.md (accepted). Infrastructure Foundation frozen. All P0 contracts stable. Per Master Plan: P1 Terminology next.

**Test status:** 1159+ baseline + P0 infra tests. 0 regression.


**Clinical Data Quality Audit (2026-07-10, read-only, ничего не изменено):** реестр `clinical_data_issues.json` (4506 записей, `pending_review`) + `clinical_data_audit_report.md` + инструмент `clinical_engine/tools/clinical_data_audit.py`. Из 294 guideline: **41 Golden-Ready кандидат**; Extraction-ошибки 235 / Normalizer 166 / Dictionary 224 / дубли title 182 gid; переэкстракция 83. SAFETY: DOSE_DAILY_MISREAD 61, DOSE_NOT_PARSED 116. PDF-подтверждён только 1638 (амоксициллин 1,5г/сут→норм. 1,5г×2=3г/сут). **Golden Case 1638 НЕ создан.**

**Milestone 13 — Release Readiness (done ✅):** Production Guard (`Engine` под `strict_mode=True` отказывается стартовать на `AUTO_GENERATED_DRAFT`/`PARTIALLY_CURATED` индексе → `EngineError(RESOURCE_NOT_CURATED)`; non-strict → warning). Test discovery: дефолтный `pytest` покрывает все подсистемы (**1141 passed, 1 xfailed** — extractor помечен xfail, не исправлялся). RFC H1 (§7.5) переоценён → рекомендация закрыть для v1 без изменений. Git-рекомендации: `RELEASE_READINESS.md` (не коммитил). Медицинская логика/алгоритмы не менялись.

**Milestone 12 — инфраструктура Golden Clinical Cases (done ✅, кейсы за врачом):** `clinical_engine/golden_cases/` (`runner.py`, `schema.json`, `_TEMPLATE.json`, `README.md`) + `clinical_engine/tests/test_golden_runner.py` (13). Раннер: кейс → `Engine.recommend()` → PASS/FAIL, read-only. Формат: `query` + `expect{13 опциональных ассертов}` + `provenance`. Реальных кейсов НЕ поставлено (guard-тест проверяет). Запуск: `python -m clinical_engine.golden_cases.runner --sqlite <normalized.sqlite>`.

**Milestone 11 — механизм врачебной курации (done ✅, ждёт врача):** `clinical_engine/tools/build_decision_ledger.py` + `build_curated_index.py` + 17 тестов + `PHYSICIAN_VALIDATION_GUIDE.md`. Никакого авто-выбора; каждый конфликт отдельно; решение врача с обязательным `decided_by`/`decided_at`/`rationale`; полный аудит-трейл; обратимость (ledger — источник истины, черновик не трогается); `PRODUCTION_CURATED` только при 0 pending и 0 invalid. Сейчас: 101 конфликт pending → `PARTIALLY_CURATED`. Ledger: `diagnosis_index_decisions.json` (редактирует врач).

**Milestone 10 — анализ конфликтов diagnosis_index (задача 1, done ✅):** `diagnosis_index_review.md` + `.json`. Из 101 конфликта: 🔴 51 critical (ICD-10 различаются) / 🟡 2 medium (ICD совпадают, КР разные) / 🟢 48 safe (вероятные дубликаты) + 28 near-dup имён (регистр/пробелы). Классификация только по фактам, БЕЗ авто-объединения/эвристик/клинических допущений — разрешение конфликтов за врачом. Data-cleanliness fix: `_split_icd10` теперь корректно парсит JSON-array-string mkb (33/265 значений). Индекс остаётся AUTO_GENERATED_DRAFT. Инструмент: `clinical_engine/tools/analyze_diagnosis_conflicts.py`.

> **Протокол хендоффа (см. `AGENTS.md` секция 0):** в конце каждой задачи любой агент/IDE обязан обновлять `AI_LOG.md` / `PROJECT_STATE.md` / `NEXT_TASK.md` / `DECISIONS.md`. Работа продолжается из любой IDE только по этим MD-файлам.

**Performance Audit (реальные данные, STRICT):** init ~29ms (<100), recommend() max 14.6ms adult / 17.4ms heavy (<50 ✅), P95 ~8ms, ~2540 recs/sec, SQL 1.23/call, peak 2.2MB. Bottleneck: `RegimenLoad` ~69% (SQL + drug_ref resolve + повторный lookup L7). Оптимизация НЕ проводилась (ждёт review). Отчёт: `performance_audit_engine.md`. Инструменты: `clinical_engine/tools/`. Draft `diagnosis_index.json` (AUTO_GENERATED_DRAFT, 895 записей, 101 конфликт) — требует врачебной курации.

**Аудит (Milestone 9):** 1 HIGH + 5 MEDIUM + 8 LOW. Кодом исправлено: M1 (allergy hardening — регистронезависимость + `ALLERGY_UNVERIFIABLE`), M3 (package-anchored пути), M5 (типизация reader'ов), L1/L2/L4/L8 (coupling/dead-code/consistency). Документацией: M2 (неточная запись), H1+M4 (per-recommendation trace/Evidence §7.5 → задокументированный gap с RFC, ждёт approval — требует изменения frozen-моделей). См. `DECISIONS.md`.

---

## Clinical Decision Engine (`clinical_engine/`)

| Milestone | Статус | Содержимое |
|-----------|--------|-----------|
| M1 — skeleton | ✅ done (2026-07-10) | `models.py` (enums + frozen dataclasses), `config.py` (EngineConfig + Profiles), `pipeline.py` (PipelineStage Protocol, PluginHook, StageContext/State/Result, ScoreWeights, ClinicalConstants). 40 тестов. |
| M2 — readers | ✅ done (2026-07-10) | `readers/sqlite_reader.py` (обёртка над `medical_normalizer.db.NormalizerDB`), `readers/drug_reference_reader.py` (`db/index.json` + pregnancy keyword-классификатор), `readers/diagnosis_reader.py` (`DiagnosisProvider` Protocol + `JsonDiagnosisProvider`), программные fixtures. 39 тестов. |
| M3 — Stages 1-2 + engine.py | ✅ done (2026-07-10) | `stages/diagnosis_match.py`, `stages/regimen_load.py` (join drug_ref + guideline_year), `engine.py` (`Engine.recommend()`, EngineMetadata/ClinicalConstants/ScoreWeights как placeholder до M5/M8/M9). 20 тестов. |
| M4 — Stages 3-4 + invariants | ✅ done (2026-07-10) | `stages/population_filter.py` (жёсткий фильтр, neonate→child flag), `stages/therapy_line_select.py` (pass-through, не фильтр — см. DECISIONS.md), `tests/test_invariants.py` (15 тестов на конституцию §12 + 2 skip-плейсхолдера для Milestone 8). 24 теста. |
| M5 — Stage 5 HardSafetyFilter | ✅ done (2026-07-10) | `stages/hard_safety_filter.py` (allergy/pregnancy/age ABSOLUTE excludes, contraindications всегда degraded WARNING — 0/40 препаратов имеют это поле), первый реальный ресурс `resources/clinical_constants.json` (allergy_class_map курирован вручную из 34→17 классов, draft, требует врачебной верификации). **Движок впервые может окончательно исключить препарат.** 21 тест. |
| M6 — Stages 6-7 DoseCalculation/DoseAdjustment | ✅ done (2026-07-10) | `stages/dose_calculation.py` (adult fixed / peds mg/kg×weight, asymmetric ambiguous-population fallback только для adult), `stages/dose_adjustment.py` (renal/hepatic — **только WARNING в v1**, hepatic-эскалация до exclude сознательно НЕ реализована — см. DECISIONS.md "never infer contraindications from free text"). 25 тестов. |
| M7 — Stage 8 InteractionCheck | ✅ done (2026-07-10) | `stages/interaction_check.py` (free-text match → всегда `UNKNOWN`, никогда не угадывается severity; CONTRAINDICATED/MAJOR/MODERATE/MINOR ветки реализованы и протестированы через monkeypatch, недостижимы без структурированных данных — но, в отличие от hepatic, это ограничение самой спеки, не наше отклонение от неё). 18 тестов. |
| M8 — Stage 9-10 RankRecommendations/Trace (финальный) | ✅ done (2026-07-10) | `stages/rank_recommendations.py` (7-компонентный скоринг, только на `state.candidates`, Invariant #3), `stages/trace.py` (outcome labeling), `resources/score_profiles/default.json`, `engine.py` — реальный `EngineMetadata` (не placeholder), `Engine.build_report()`. **Движок теперь возвращает полностью ранжированный `RecommendationSet`.** 30 тестов, 0 skip. |
| M9 — Audit remediation | ✅ done (2026-07-10) | Устранены замечания независимого аудита: M1 (allergy hardening), M3 (package-anchored пути), M5 (типизация reader'ов), L1/L2/L4/L8. H1+M4 → задокументированный gap с RFC. +3 теста. `clinical_engine/_population.py` (нейтральный helper). |
| Perf Audit | ⏳ next | `Engine.recommend()` на реальной `metadata.sqlite` (2675 схем), цель <50ms (§9.1) |
| Golden cases | ⏳ | Doctor-reviewed golden cases, production `diagnosis_index.json`, врачебная верификация `allergy_class_map` |
| Flutter | ⏳ | интеграция после verification |

**Известный риск (подтверждён проверкой всех 40 препаратов в Milestone 2, не блокирует — degraded-mode принят как решение):** `renal_adjustment`/`interactions` — свободный текст (передаётся как есть, не парсится). `contraindications` и `pediatric_dosing` отсутствуют у **всех** 40 препаратов. Generic `age_restriction_max` тоже отсутствует. `pregnancy_category` — свободный текст, но приведён к enum узким keyword-классификатором в `DrugReferenceReader` (см. DECISIONS.md). Итог: HardSafetyFilter (CI-проверка), DoseCalculation (peds mg/kg) будут в degraded WARNING mode для этих полей в v1 — ожидаемо, задокументировано.

**Известный риск (Milestone 5, задокументирован):** `allergy_class_map` в `resources/clinical_constants.json` — ручная курация 34 узких `class`-строк из `db/index.json` в 17 канонических аллергенных классов (объединены только generation/route-подварианты одного семейства — пенициллины, цефалоспорины, макролиды, фторхинолоны). Черновик, требует врачебной верификации перед production-использованием (см. DECISIONS.md).

**Известный пробел (Milestone 6, задокументирован):** `pediatric_dosing` отсутствует у всех 40 препаратов → пед. дозирование всегда `PEDS_DOSING_UNKNOWN` на реальных данных. `hepatic_adjustment`/`renal_adjustment` — свободный текст у всех препаратов, где присутствуют (15/40 и 29/40 соответственно) → Stage 7 всегда в degraded WARNING-режиме, дозу численно не корректирует, hepatic никогда не исключает препарат в v1 (сознательное решение, не пробел реализации — см. DECISIONS.md).

**Известный пробел (Milestone 7, задокументирован):** `interactions` — свободный текст у 32/40 препаратов, структурированного поля нет вообще. InteractionCheck поэтому всегда даёт `UNKNOWN` severity при текстовом совпадении, никогда MAJOR/MODERATE/MINOR/CONTRAINDICATED на реальных данных — это ограничение самой спецификации (§6.4 явно резервирует классификацию severity для preparation-time structured данных), не наше решение отступить от неё.

**Осознанно не реализовано (Milestone 8, задокументировано, не архитектурный пробел):**
- Confidence propagation (§7.3) — `Recommendation.confidence`/`confidence_breakdown` на дефолтах
- Plugin hooks — enum существует, registry нет
- 4 из 5 score profiles (ent/urology/icu/pediatrics) — content-задача
- `guideline_version` в `EngineMetadata` — `"unversioned"`, ждёт production `diagnosis_index.json`

**Тесты:** дефолтный `pytest` → **1159 passed, 1 xfailed** (0 регрессий после P0-1 тестов). Пре-existing xfailed только в extractor.

---

## Компоненты

### Приложение (antibio-calc)
| Компонент | Статус |
|-----------|--------|
| База препаратов (28 шт) | ✅ 85% |
| База нозологий (46 шт) | ✅ 85% |
| Схема БД (schema.json) | ✅ 100% |
| Build-скрипт c валидацией (build_db.ps1 + build_html.ps1) | ✅ 100% |
| Валидация целостности БД (validate_db.js) | ✅ 100% |
| Сборка БД (db/build_db.ps1) | ✅ 100% |
| UI — поиск нозологий | ✅ |
| UI — выбор препарата/формы/дозы | ✅ |
| UI — расчёт доз (мг/мл) | ✅ |
| UI — разведение инъекций | ✅ |
| UI — печать рецепта (латынь) | ✅ 100% |
| Клиентская валидация БД (validateDB в init()) | ✅ 100% |
| UI — история расчётов | ✅ |
| UI — тёмная тема | ✅ |
| UI — адаптив (мобильный/десктоп) | ✅ |
| Копирование назначения | ✅ |
| Тесты | ❌ Нет |
| CI/CD | ❌ Нет |
| Документация разработчика | ✅ Создана |

### Pipeline (извлечение КР → knowledge_base.json)
| Компонент | Статус |
|-----------|--------|
| Загрузчик PDF (clinrec_downloader) | ✅ 2000+ PDF |
| Классификатор (antibiotic_gate) | ✅ A/B/C/D уровни |
| LLM-экстракция (extract_raw) | ✅ 294/361 A+B (81.4%) — 67 осталось |
| Валидация LLM (validate) | ✅ mock (реальная: ждёт API) |
| Сборка knowledge_base.json | ✅ 294 guidelines, 2675 regimens |
| SQLite (metadata.sqlite) | ✅ 2675 regimens (без дубликатов) |
| Prefilter (prefilter.py) | ✅ классификация 2000 PDF за 0.17с |
| Audit no_antibiotics | ✅ 305 → 298 (7 перемещены) |
| Дубликаты-конфликты | ✅ 17 decisions унифицированы (11 filenames) |
| Sync (misplaced PDFs) | ✅ 0 misplaced, 1893 manifest entries |
| Quarantine | ✅ 2 orphans → quarantine/ |
| Crash safety (fsync + checkpoint) | ✅ per-PDF + every-10 checkpoint |
| Restore_archived_pdfs.py | ✅ создан |
| Deep audit | ✅ PASS (0 issues, 4 warnings) |

### Medical Normalizer (`medical_normalizer/`)
| Модуль | Статус | Тесты |
|--------|--------|-------|
| models.py | ✅ | — |
| dictionary.py | ✅ | ✅ |
| drug_parser.py | ✅ | ✅ |
| dose_parser.py | ✅ | ✅ |
| route_parser.py | ✅ | ✅ |
| frequency_parser.py | ✅ | ✅ |
| duration_parser.py | ✅ | ✅ |
| population_parser.py | ✅ | ✅ |
| therapy_line_parser.py | ✅ | ✅ |
| confidence.py | ✅ 100% coverage | ✅ 130 тестов |
| validator.py | ✅ 100% coverage | ✅ 164 теста |
| normalizer.py | ✅ 100% coverage | ✅ 134 теста |
| db.py | ✅ 99% coverage | ✅ 121 тест |
| **Итого medical_normalizer** | **✅ COMPLETE** | **726 тестов** |

**Тесты medical_normalizer:** 726/726 pass (`pytest medical_normalizer/tests/ -q`)

**Integration test (80 regimens из knowledge_base.json):**
- PASS: 24 (30.0%), REVIEW: 10 (12.5%), REJECT: 46 (57.5%)
- Confidence: min=0.200, max=0.919, mean=0.615, median=0.704
- Главные REJECT: REQUIRED_MISSING (route/frequency/dose не извлечены LLM)
- Главные REVIEW: DRUG_UNKNOWN (препарат не в словаре)
- Все 80 regimens сохранены в SQLite через NormalizerDB.save_many()

---

## Рабочие папки

- `downloads_active/` — 477 PDF для LLM-экстракции
- `archive_review/` — 361 PDF требующие ручного просмотра
- `archive_no_antibiotics/` — 123 PDF без антибиотиков
- `quarantine/` — 2 orphan PDF (неопознанные)
- `downloads_all/` — пусто (все PDF распределены)

## LLM-провайдер

- **Активный:** DeepSeek V4 Flash через opencode.ai/zen (opengo tariff). Работает (HTTP 200).
- **Резервный:** Anthropic claude-sonnet-4-20250514 через vip.j3gb.com (429 daily quota).
- **Неактивные:** openrouter, openai, gemini, ollama, vllm, local — без API-ключа.
- **Модели:** extraction=deepseek-v4-flash, validation=deepseek-v4-flash.
- **max_tokens:** 8192 (для reasoning model).

## Команды main.py

| Команда | Назначение |
|---------|-----------|
| `python main.py doctor` | Health check (read-only) |
| `python main.py sync` | Fix misplaced PDFs, rebuild manifest |
| `python main.py dedup` | Resolve conflicting duplicates in dry_run_manifest |
| `python main.py quarantine` | Move orphan PDFs to quarantine/ |

## Deep Audit (2026-07-09)

**Результат:** V PASS — 0 issues, 27 checks passed

**Предупреждения (4, все приемлемы):**
1. 747 regimen pairs с одинаковым (antibiotic,dose,route,freq) — разные duration/age — не ошибка
2. Quarantine: 2 orphan PDFs (unknown origin)
3. 67 A+B items не экстрагированы (нет релевантного текста или LLM не может обработать)
4. 133/2675 regimens без section_name (5%)

## Quality Audit (2026-07-09)

**Полный аудит 2675 regimens через MedicalNormalizer:**

| Метрика | Значение |
|---------|----------|
| Total regimens | 2675 |
| Total guidelines | 294 |
| PASS | 880 (32.9%) |
| REVIEW | 320 (12.0%) |
| REJECT | 1475 (55.1%) |
| Confidence mean | 0.6312 |
| Confidence median | 0.7044 |
| Performance | 8800 regimens/s |
| Parser errors | 20/2675 (0.7%) |

**Field completeness (после нормализации):**
| Поле | % |
|------|---|
| Drug | 100% |
| Dose | 71.1% |
| Route | 65.1% |
| Frequency | 56.6% |
| Duration | 41.0% |
| Therapy line | 60.1% |
| Pregnancy | 2.6% |
| Renal adjustment | 2.8% |
| ATC code | 0% |

**Сгенерированные файлы:**
- `quality_report.md` — полный отчёт
- `quality_root_cause.md` — Root Cause Analysis (3 отчёта + рекомендация)
- `field_statistics.csv` — статистика по полям
- `unknown_drugs.csv` — 441 неизвестный препарат
- `dictionary_expansion.md` — рекомендации (~160 записей)
- `production_readiness.md` — оценка готовности

## Root Cause Analysis (2026-07-09)

**Per-regimen нормализация 2675 regimens + классификация origin/recoverability.** См. `quality_root_cause.md`.

### Главные выводы (приоритеты пересмотрены)

| Источник | Доля REJECT-причин | Что нужно |
|----------|-------------------:|-----------|
| **LLM extraction** | 75% (2153/2869 required-missing) | LLM re-extraction (high cost) |
| **Normalization** | 25% (716/2869 required-missing) | Parser expansion (low cost) |
| Dictionary | 0% REJECT (1166 REVIEW) | Dictionary expansion (REVIEW only) |

### REJECT breakdown (per-regimen overlap анализ, baseline)

| Группа | Regimens | Recoverability |
|--------|---------:|----------------|
| Parser-only flippable | 403 | parser fix (low cost) |
| Partial (norm + llm) | 281 | parser fix + LLM re-extract |
| LLM-only | 791 | только LLM re-extraction |

## Parser Improvements (Tasks 1-4) — MEASURED (2026-07-09)

**TDD, 4 задачи, 803/803 тестов (+77 new).** См. `quality_audit_after_parsers.md` для полного comparison.

### Verdicts — baseline vs after

| Verdict | Baseline | After | Δ |
|---------|---------:|------:|---:|
| PASS | 880 (32.9%) | 1039 (38.8%) | **+159** |
| REVIEW | 320 (12.0%) | 443 (16.6%) | +123 (REJECT→REVIEW, drug_unknown exposed) |
| REJECT | 1475 (55.1%) | 1193 (44.6%) | **-282** |
| Confidence mean | 0.6312 | 0.7188 | **+0.0876 (+13.9%)** |
| Parser errors | 20 | **0** ✅ | -20 |

### Fields recovered

| Поле | Baseline missing | After missing | Recovered |
|------|----------------:|--------------:|----------:|
| frequency | 1160 | 706 | **454** |
| duration | 1578 | 951 | **627** |
| therapy_line | 1067 | 0 | **1067** |
| dose | 774 | 754 | 20 |
| **Total** | — | — | **2168** |

### Per-task (TDD, measured)

| # | Task | Файл | +Tests | Recovered | ΔREJECT | ΔConf |
|---|------|------|-------:|-----------:|--------:|------:|
| 1 | FrequencyParser | frequency_parser.py | 42 | freq -454 | -274 | +0.0254 |
| 2 | DurationParser | duration_parser.py | 19 | dur -627 | 0 | +0.0174 |
| 3 | TherapyLineParser | therapy_line_parser.py | 7 | tl -1067 | 0 | +0.0437 |
| 4 | Type guards | drug_parser.py | 9 | errors -20, dose -20 | -8 | +0.0011 |

### REJECT breakdown — after

| Группа | Baseline | After | Δ |
|--------|---------:|------:|---:|
| Parser-only flippable | 403 | 118 | -285 |
| Partial | 281 | 111 | -170 |
| LLM-only | 791 | 961 | +170 (reclassified) |
| No required-missing | 0 | 3 | +3 |

**Parser improvements исчерпаны на ~71% (285/403).** Оставшиеся 118 — hard edge cases, diminishing returns.

### Origin shift

| Источник | Baseline | After | Δ |
|----------|---------:|------:|---:|
| Normalization | 772 | 298 | **-474 (-61%)** |
| LLM extraction | 3055 | 3055 | 0 |
| Dictionary | 3848 | 3842 | -6 |
| Missing source | 5206 | 5206 | 0 |

## Medical Dictionary subsystem (2026-07-09) ✅

**Independent terminology database.** См. `medical_dictionary/metadata.json`.

| Файл | Schema | Entries | Loaded by |
|------|--------|--------:|-----------|
| drug_synonyms.json | synonym→canonical | 152 | dictionary.py |
| drug_atc.json | canonical→ATC | 0 (pending review) | dictionary.py |
| drug_groups.json | group→ATC prefix | 0 (pending review) | dictionary.py |
| route_dictionary.json | synonym→canonical | 41 | dictionary.py |
| unit_dictionary.json | synonym→canonical | 28 | dictionary.py |
| frequency_dictionary.json | pattern descriptors | 41 | none (reference) |
| duration_dictionary.json | pattern descriptors | 33 | none (reference) |
| pregnancy_dictionary.json | keyword patterns | — | none (reference) |
| renal_dictionary.json | keyword patterns | — | none (reference) |
| metadata.json | inventory | — | — |
| unknown_drugs.csv | ranked unknowns | 441 | — |
| dictionary_candidates.json | review candidates | 441 (all pending_review) | — |

**dictionary.py rewrite:** hardcoded dicts removed, loads via `medical_dictionary.loader`. Module-level names preserved (DRUG_SYNONYMS, ROUTE_SYNONYMS, UNIT_NORMALIZATION + new DRUG_ATC, DRUG_GROUPS). Class logic unchanged. No parser logic changes.

**Measured (STEP 5, no regression):** PASS 1039, REVIEW 443, REJECT 1193, confidence 0.7188 — identical to pre-refactor.

**Тесты:** 823/823 medical_normalizer (+20 loader tests). Pipeline 55 pass / 1 pre-existing fail (extraction, unrelated).

**Review policy:** never auto-accept. All 441 candidates `pending_review`. Человек ревьюит → accepted/rejected → entries в drug_synonyms.json / drug_atc.json.

## Оставшиеся задачи (приоритет пересмотрен per measured results)

### Critical (REVIEW↓ + PASS↑, low cost) — next
1. **DRUG_SYNONYMS expansion** (~60 synonyms) — REVIEW 443→~5-50, 438 drug-only flippable → PASS
2. **DRUG_ATC mapping** (~75 drugs → ATC codes) — ATC 0%→~80%, confidence↑

### High (REJECT↓, high cost)
3. **LLM re-extraction** (improve prompt, re-run 294 PDF) — 961 LLM-only REJECT, единственный путь к REJECT 25%

### Medium/Low
4. Remaining parser edge cases (118 parser-flippable REJECT, diminishing returns)
5. Drug groups handling (фторхинолоны → ATC group)
6. Combination drug normalization ([...] brackets)
7. Typo correction
8. Real LLM validation (replace mock, 130 IDs)
9. Golden case tests (app)
10. PostgreSQL migration (for >10k)
11. Multiprocessing (for >50k)
12. CI/CD pipeline
