# ROADMAP — ANTIBIO

## Current milestone — P5.6 Production Recovery + Clinical Review Workbench

Status: **ACCEPTANCE / NOT COMPLETE** (2026-07-30). Credential rotation and
the historical fresh-clone gate are closed. C7 source-fidelity review is
closed. The exact secret-free, production-data-free C7/audit boundary is
committed as `60e6033`; locked-dependency fresh-clone verification and
publication remain, and `main` is 35 commits ahead of `origin/main`. P6 is
BLOCKED pending real physician
approvals, completed pilot cases, approved-data Golden pass, shadow
validation, safety gates, request audit snapshot, and explicit owner
approval.

Historical roadmap retained below.

> Жизненный цикл проекта. Мгновенный контекст для любой IDE/модели: где проект, что завершено, что дальше.

**Текущая версия:** v0.4 — Quality Improvement 🔄 (parser tasks done, Medical Dictionary subsystem done, awaiting manual review of 441 candidates)
**Обновлено:** 2026-07-09

---

## Версии

| Версия | Этап | Статус | Дата |
|--------|------|--------|------|
| v0.1 | PDF Downloader | ✅ | 2026-07-07 |
| v0.2 | Knowledge Extraction | ✅ | 2026-07-09 |
| v0.3 | Medical Normalizer | ✅ | 2026-07-09 |
| **v0.4** | **Quality Improvement** | **✅ + P1 Terminology (P1-B CLOSED)** | **2026-07-11** |
| P2-1 | Conformance-validator | ✅ COMPLETE + FROZEN (additive) | 2026-07-11 |
| P2-2 | Coverage metrics (A/B/C) | 🔄 Analysis only (P2-2_..._Analysis.md) | 2026-07-11 |
| v0.5 | ATC Mapping | ⏳ | pending |
| v0.6 | LLM Re-Extraction v2 | ⏳ | pending (decision after v0.4) |
| v0.7 | Flutter Integration | ⏳ | planned |
| v0.8 | Clinical Decision Engine | ⏳ | planned |
| v1.0 | ANTIBIO Release | ⏳ | goal |

---

## Детали по этапам

### v0.1 — PDF Downloader ✅
- 963 уникальных PDF скачано с API Минздрава РФ
- Классификация A/B/C/D (2000 PDF за 0.17с)
- 477 active / 361 review / 123 no_abx / 2 quarantine

### v0.2 — Knowledge Extraction ✅
- LLM extraction (DeepSeek V4 Flash): 294 guidelines, 2675 regimens
- knowledge_base.json + metadata.sqlite
- Mock validation (164 IDs; real validation pending for 130 IDs)

### v0.3 — Medical Normalizer ✅
- 13 модулей, 726/726 тестов, 99.9% coverage
- Confidence weighted (required=3, important=2, optional=1)
- Validator: PASS/REVIEW/REJECT
- NormalizerDB (SQLite, UPSERT preserves manual fields)
- Performance: 8800 regimens/s

### v0.4 — Quality Improvement 🔄
**Цель:** снизить REJECT 55%→40%, REVIEW 12%→7%, PASS 33%→48% (без LLM re-extraction).

**Quality Audit baseline (2675 regimens):**
- PASS 880 (32.9%) / REVIEW 320 (12.0%) / REJECT 1475 (55.1%)
- Confidence mean 0.6312
- Parser errors 20/2675 (0.7%)

**Root Cause Analysis:**
- REJECT драйвер: REQUIRED_MISSING (2869) — dose/route/frequency
  - LLM extraction 75% (2153, raw отсутствует)
  - Normalization 25% (716, raw есть, parser gap)
- REVIEW драйвер: DRUG_UNKNOWN (1166) — dictionary gap
- Per-regimen: REJECT 1475 = 403 parser-flippable + 281 partial + 791 LLM-only

**Parser Improvements (Tasks 1-4) — MEASURED ✅:**
- PASS 880→1039 (+159), REVIEW 320→443 (+123 REJECT→REVIEW), REJECT 1475→1193 (-282)
- Confidence 0.6312→0.7188 (+13.9%), parser errors 20→0 ✅
- 2168 fields recovered (freq -454, dur -627, tl -1067, dose -20)
- Tests 726→823 (+97, TDD)
- Parser improvements исчерпаны ~71% (285/403 REJECT-flippable)

**Medical Dictionary subsystem — ✅ (2026-07-09):**
- `medical_dictionary/` — independent terminology DB (10 JSON + loader.py)
- `dictionary.py` rewritten: loads JSON via loader, module-level names preserved, class logic unchanged
- `unknown_drugs.csv` — 441 unknown drugs ranked by occurrence
- `dictionary_candidates.json` — 441 candidates, ALL `pending_review` (never auto-accept)
- Measured: PASS 1039, REVIEW 443, REJECT 1193, conf 0.7188 — identical to pre-refactor (no regression)
- Tests: 823/823 pass (+20 loader tests)

**Подзадачи (по priority):**
1. ✅ FrequencyParser expansion — 454 recovered (83%)
2. ✅ DurationParser expansion — 627 recovered (74%)
3. ✅ TherapyLineParser expansion — 1067 recovered (100%)
4. ✅ Parser type guards — 20 errors → 0
5. ✅ Medical Dictionary subsystem — terminology DB extracted from Python, no regression
6. ⏳ Manual review of 441 candidates (человек) → accepted/rejected
7. ⏳ DRUG_SYNONYMS expansion (по accepted) — 438 drug-only REVIEW → PASS
8. ⏳ DRUG_ATC mapping (по accepted с possible_atc) — ATC 0%→80%

**Критерий выхода:** dictionary/ATC завершены → decision по LLM re-extraction (v0.6).

### v0.5 — ATC Mapping ⏳
- DRUG_ATC dict (~75 drugs → ATC codes)
- Drug groups → ATC prefix (фторхинолоны J01MA, карбапенемы J01DH)
- ATC coverage 0% → ~80%
- Confidence boost

### v0.6 — LLM Re-Extraction v2 ⏳ (отдельный проект)
**Старт:** только если после v0.4+v0.5 REJECT всё ещё доминирует missing extraction fields.
- Переписать extraction prompt
- Re-run 294 PDF
- Пересобрать KB, re-normalize
- Цель: REJECT 40%→25%
- **НЕ начинать автоматически.** Decision point после v0.5.

### v0.7 — Flutter Integration ⏳
- Mobile app для врачей
- Offline-first, локальная БД
- Sync с knowledge_base

### v0.8 — Clinical Decision Engine ⏳
- Rule engineповерх normalized regimens
- Patient context → recommended regimen
- Drug interaction checks
- Allergy / renal / pregnancy adjustments

### v1.0 — ANTIBIO Release ⏳
- Production-ready система
- Validated against golden cases
- CI/CD, monitoring, PostgreSQL (if >10k)

---

## P4 — Document Intelligence Platform ✅ COMPLETE (2026-07-13)

**Status:** Production Ready. Big release closed.

**Subphases:**
- P4.1 Multi-Engine Extraction ✅
- P4.2 Layout Intelligence ✅ (P4.5 FINAL CLINICAL ACCEPTANCE AUDIT PASSED 2026-07-13)
- P4.3 Medical Semantic Intelligence ✅

**P4.5 Audit (2026-07-13):** A) PASSED. 193 PDFs, 20 structured tables representative, clinical cell recovery measured, 0 FPs, regressions clean. P4.4 authorized. Full report: P4.5_PRODUCTION_AUDIT.md.

**Verified (real runs):**
- Router + cache + provenance
- Semantic layer (entities, norm, kobj, relations, consistency)
- Fallback paths (mineru/mixed)
- Real PDFs (328+ ents on guideline, 338 on test.pdf)
- 10/10 tests pass
- No raw text to downstream

**Goal:** PDF → Extraction → Semantic Objects. System no longer parses PDFs directly for knowledge.

**Rationale:** Enterprise releases. P4 fully closed as Document Intel Platform.

Future rule: every rec + separate validation prompt + real audit.

## P4.4 Production Knowledge Base ✅ CERTIFIED 2026-07-15 (real exec, full audit)

**Final verified state (supersedes earlier-in-page draft numbers below):** 192/192 corpus PDFs,
31,336 objects, 100,854 provenance rows, 0 blocking invariants, regression 72 passed/0 failed. Full
evidence: `PRODUCTION_SCORECARD.md`, `PROVENANCE_CERTIFICATION.md`,
`P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md`. Scope caveat: RC-019 — Clinical Decision Engine does not
yet consume this KB; resolving that is P5/P6 scope, not a P4.4 blocker.


**Goal achieved:** System independent of PDFs for knowledge.

PDF → Extraction → Semantic Objects → Versioned KB

**Implemented (real runs on guideline PDFs):**
- Immutable frozen KnowledgeObject + Provenance
- Versioning (v1 active, superseded on change)
- Full source lineage (pdf/page/extractor/semantic)
- Cross-doc dedup (merge provenance on same key)
- Conflict detection (record + queue review)
- Deterministic merge (new version)
- Human Review Queue (conflict/low-val)
- Validation (basic + full)
- Impact Analysis (affected keys from new doc)

**Benchmark (real):**
- On real 36p guideline: ~100+ objects from ~328 ents
- Dedup/conflicts/reviews triggered
- Time: seconds per doc
- Validation: mostly valid
- See P4.4_PRODUCTION_AUDIT.md

No KG (per spec, only if needed later).

Production Ready for KB layer.

## P5 — Medical Knowledge Platform ⏳

(incorporates P4.4 + full consistency, golden KB validation)

## P6 — Clinical Decision Support Platform ⏳

## P7 — Production Ecosystem ⏳

## P5 — Medical Knowledge Platform ⏳

Goals:
- Full semantic normalization
- Knowledge consistency
- Versioning
- Golden validation
- No Clinical Engine changes.

## P6 — Clinical Decision Support Platform ⏳

- RAG, explainability
- AI assistants
- Human review
- Versioning

## P7 — Production Ecosystem ⏳

- API, UI
- Monitoring, security
- CI/CD, scaling

## Принципы (updated)

### P4.4 Unified Document Model
- Single internal `Document` / `Page` representation independent of engine (source, pages, full_text, metadata, confidence, tables, provenance).
- Parser / downstream always sees unified, engine-agnostic.

### P4.5 Extraction Router
- Quality gate + per-page decisions.
- Try primary, fallback engines in order.
- Extensible registry for new engines.

### P4.6 Confidence Pipeline
- Every stage (engine, layout, table, field) returns confidence.
- Aggregated at document / field level.

### P4.7 Provenance v2
- Every extracted field / page records:
  - source_pdf
  - page
  - coordinates / bbox (if available)
  - extraction_engine (pymupdf | mineru | docling)
  - confidence
  - document_version / timestamp
- Stored in Document.metadata["page_provenance"] and per-field.

**Current status (2026-07-13):** P4.1 COMPLETE. Docling integrated into router as third engine. Registry updated. All produce same Unified Document. Real multi-engine benchmark done (pymupdf fast primary, docling rich output, mineru OCR). Routing rec: pymupdf primary + quality gate + mineru/docling fallbacks. See extraction README for tables.

**Do not bypass unified model. All document work goes through router → unified Document.**

**Extensibility:** New engines register in router; no change to Parser or clinical layers.

---

## Принципы

- **Architecture FROZEN** с v0.3 — не рефакторить, только additions
- **Measure, don't estimate** — каждый этап измеряется quality audit'ом
- **TDD** для всех parser/dictionary изменений
- **Documentation** обновляется после каждой завершённой подзадачи
