# ANTIBIO — Architecture v3 (Reference Architecture)

> **Статус:** ПРИНЯТО как официальная базовая архитектура (2026-07-10). Изменения — только при реальной инженерной причине, обнаруженной при реализации (RFC).
> **Не пересматривать:** extraction, normalization, SQLite-схема, Medical Dictionary — CLOSED.
> Консолидирует: Architecture Design Document (C) + Architecture Review v2 (Δ1–Δ10) + Final Benchmark (v3 reference layers).

---

## 1. Архитектурные принципы (законы проекта)

Извлечены из неявных допущений v1 и приняты как явные принципы. Вся архитектура подчинена им.

| # | Принцип |
|---|---|
| **P1** | Разделение Knowledge Acquisition (PDF→extraction→normalize→SQLite) и Clinical Reasoning. |
| **P2** | Детерминированное reasoning-ядро без побочных эффектов: `(Query, KnowledgeSnapshot, Config) → RecommendationSet`. Identical inputs → identical outputs. |
| **P3** | Иммутабельные версионированные снимки знаний (reproducibility over freshness). |
| **P4** | Безопасность — жёсткий шлюз, ортогональный ранжированию. Unknown ≠ safe, unknown ≠ contraindicated. Degraded → WARNING, никогда silent-exclude. |
| **P5** | Верховенство врача: система — decision support, не decision maker; каждое клин-утверждение прослеживается к одобренному человеком источнику. |
| **P6** | Полная provenance: любой выход объясним до исходного документа и версии данных. |
| **P7** | Честная деградация с явной неопределённостью; неполнота не скрывается. |
| **P8** | Offline-first, самодостаточность; ядро не зависит от сети в рантайме. |
| **P9** | Curation-статус — принудительный жизненный шлюз (DRAFT→CURATED→PRODUCTION); Production Guard. |
| **P10** | Therapy-class-neutral ядро; терапия-специфика — данные/плагины, не код. |
| **P11** | Один источник истины на домен; нет дублирующей авторитетности. |
| **P12** | Open for extension, closed for modification (порт/плагин/данные, не правка frozen-ядра). |

---

## 2. Выбранная архитектура: Ports & Adapters / Knowledge-as-Data (вариант C)

Сравнивались: A (эволюция монолита), B (knowledge-graph-centric), **C (ports & adapters)**. Выбрана **C** — единственная, удерживающая все 12 принципов одновременно и делающая вариативность данными за портами.

**Формула:** *Reasoning-ядро — константа. Вся вариативность (объём, специальности, юрисдикции, класс терапии, качество STTR) — иммутабельные версионированные бандлы знаний за портами.*

Граф (B) допустим как ВНУТРЕННИЙ адаптер представления, не затрагивая ядро.

---

## 3. Слои v3 (reference layers, каждый — на прецеденте)

| Слой | Что | Прецедент |
|---|---|---|
| **Execution Kernel** | 10-стадийное детерминированное ядро v1 (сохранить) | уникальная сила ANTIBIO |
| **Guideline Logic Layer** | guideline = decision-network (eligibility-criteria + actions), CQL-shaped; как ДАННЫЕ | FHIR Clinical Reasoning (PlanDefinition/ActivityDefinition) / PROforma / GLIF3 |
| **Terminology Binding** | ATC (препараты), ICD-10 primary + SNOMED interop; ValueSet/ConceptMap | FHIR Terminology / OpenMRS concept dict / SNOMED / ATC |
| **Knowledge Artifacts** | версионируемые Library-бандлы: RegimenBundle, SafetyBundle, RoutingBundle, InteractionBundle, ConstantsBundle, ScoreProfileBundle, LogicBundle, TerminologyBundle | FHIR Library / CQL versioning |
| **Evaluation & Assurance** | golden + coverage(A/B/C) + drift + faithfulness; conformance бандлов | FHIR Measure + Inferno + DSPy |
| **Offline + Sync** | embedded store + sync + forced-recall/expiry для safety | Bahmni Connect / OpenMRS sync |
| **Search** | embedded semantic (LanceDB-класс) + terminology-bound matching; GraphRAG — explanation | LanceDB / GraphRAG / LlamaIndex |
| **Integration** | CDS Hooks (inbound) + FHIR resources (outbound) | CDS Hooks / SMART on FHIR |
| **Provenance** | цепочка recommendation→bundle-hash→source→human-signature + AI-provenance | FHIR Provenance / W3C PROV |
| **Governance** | RBAC (curator/reviewer/safety-officer/medical-director) + event-sourced ledger + FHIR status | OpenMRS/OpenCDS + FHIR publication-status |
| **AI/Plugins** | hook-точки + determinism-contract (выход стохастика фиксируется в decision-record) | CDS Hooks services / DSPy |

---

## 4. Ключевые архитектурные решения (Review v2, Δ1–Δ10)

- **Δ1 Guideline Logic Layer** — guideline это дерево решений (терапевтическая таблица), не плоский список. STTR реконструирует именно структуру. (Самое глубокое изменение.)
- **Δ2 Terminology Binding** — ATC заменяет ручной allergy_class_map; терминология ОТДЕЛЬНЫМ слоем (урок Arden «curly-braces problem»: не вшивать data-binding в логику).
- **Δ3 Evaluation Layer** — metric-driven, иначе curated тихо деградирует.
- **Δ4 Coverage / Negative-Knowledge** — A/B/C в рантайме; «нет данных» vs «не покрыто».
- **Δ5 Offline Safety-Freshness** — hard-expiry + forced-sync для recall (stale-but-recalled — критичный offline-риск).
- **Δ6 Embedded semantic search** — чинит хрупкий exact-match диагнозов.
- **Δ7 Deterministic-plugin contract** — стохастический AI не ломает P2/P3 (captured output).
- **Δ8 RBAC + separation-of-duties** — кто реконструировал ≠ кто утвердил.
- **Δ9 Cryptographic provenance chain**.
- **Δ10 Table-aware ingestion & RAG** (RAGFlow-frame); GraphRAG — explanation-адаптер.

---

## 5. Устойчивость к росту

| Сценарий | Поглощается | Ядро меняется? |
|---|---|---|
| 2675→5000+ regimens | больше строк в RegimenBundle | Нет |
| 294→3000+ guidelines | больше бандлов + партиции + search-index | Нет |
| Новые специальности | specialty-теги + score-profiles (данные) | Нет |
| Non-antibiotic | Therapy-category (P10) + новые SafetyBundle | Нет |
| Международные КР | jurisdiction-tagged бандлы + terminology-binding | Нет |
| STTR улучшает extraction | новые DRAFT-бандлы → review-ledger → curated | **Нет** |

---

## 6. Границы (что v3 НЕ делает)
- Не переписывает extraction/normalization/SQLite-схему (CLOSED).
- Не берёт тяжёлый rule-engine (урок OpenCDS/Drools) — ядро остаётся чистой детерминированной функцией.
- Не вшивает data-bindings в guideline-логику (урок Arden).
- Не делает LLM/RAG частью decision-path (P2/P4).
- Не делает граф-БД offline-ядром (P8).

**Что ANTIBIO уже делает ЛУЧШЕ индустрии:** детерминированный safety-gate, воспроизводимость, provenance до source-quote, enforced curation-status, executor-agnostic AI-containment.
**Где отстаёт (что достраивает v3):** guideline-logic, terminology-services, standard interop (FHIR/CDS Hooks), sync-зрелость, conformance-тестирование.
