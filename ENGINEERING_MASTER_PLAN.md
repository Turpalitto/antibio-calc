# ANTIBIO — Engineering Master Plan

> **Статус:** ПРИНЯТО (2026-07-10) как базовый execution-план. Основано на `ARCHITECTURE_V3.md`.
> Дисциплина: инкрементально, каждый этап независимо тестируем, **ядро v1 не переписываем**; новое — порты/данные/адаптеры за флагами; откат = отключить адаптер.

## Принципы исполнения
- **Kernel frozen** на всех этапах.
- **Measure before change** — eval-harness строится рано (Phase 2).
- **Additive + feature-flag** — тривиальный откат.
- **Data/content track параллелен** и гейтит production (STTR, курация — не код).

---

## Этапы (Phase 0–9)

Каждый этап специфицирован: Goal · Deliverables · Dependencies · Must-exist · Must-NOT-yet · Risks · Acceptance/Validation · Regression · Rollback · Complexity. Полные карточки — в исходном плане; здесь — сводка.

- **Phase 0 — Knowledge Foundation** *(foundation, Medium)*: порты поверх ридеров + BundleManifest + versioning + verified loader. Must NOT: FHIR/sync/terminology/logic. Acceptance: движок через порты идентичен, 0 regression, loader верифицирует хеш, Production Guard читает status из manifest.
- **Phase 1 — Terminology Binding** *(foundation, Med-High)*: ATC/ICD-10 binding; allergy-класс из ATC (fallback на ручной map); ValueSet/ConceptMap. Acceptance: класс через ATC для ≥40 препаратов; снижение exact-match отказов; safety green.
- **Phase 2 — Evaluation & Assurance** *(foundation, Medium)*: conformance-validator + coverage(A/B/C) + regression-baseline + golden в CI. Acceptance: coverage воспроизводит 58/233/3; baseline зафиксирован.
- **Phase 3 — Guideline Logic Layer** *(Very High, post-MVP)*: guideline как decision-network (данные); criteria-evaluator + порт; coexist с flat. Acceptance: пилот 1638 отвечает на аллергию/рецидив по КР; flat не затронут.
- **Phase 4 — Governance** *(Medium)*: event-sourced ledger + RBAC + separation-of-duties + promotion-gate DRAFT→CURATED→PRODUCTION.
- **Phase 5 — Provenance + Confidence** *(High)*: per-recommendation Evidence (RFC H1) + provenance-chain + §7.3 confidence. Требует переоткрытия RFC H1.
- **Phase 6 — Search** *(Med-High)*: embedded semantic (LanceDB-класс) + terminology-bound matching; никогда silent no-match.
- **Phase 7 — Offline + Sync + Freshness** *(High, MVP-gate)*: packaging+signing + sync + forced-recall/expiry + last-synced.
- **Phase 8 — Integration (CDS Hooks + FHIR)** *(High, postpone)*.
- **Phase 9 — AI/Plugins/RAG** *(High, postpone)*: determinism-contract + RAG grounding + GraphRAG explanation.

### Параллельный Data/Content track (гейты production, не platform-код)
- **DQ-A** RCA Phase A (preprocessing/tokenizer/dictionary + duration re-normalization) — gate: Phase 2. ⚠️ трогает сейчас-FROZEN нормализатор/словарь → требует un-freeze-решения.
- **DQ-B** STTR (реконструкция таблиц) — отдельный проект; питает Phase 3/4.
- **DQ-C** Врачебная курация LEVEL A (58) + dedup diagnosis_index + верификация allergy — gate: Phase 4; человеческая задача.

---

## Milestone Table

| Phase | Milestone | Foundation? | Complexity | Гейтит |
|---|---|---|---|---|
| 0 | Ports + Bundle + Versioning | ★ | Medium | всё |
| 1 | Terminology (ATC/ICD) | ★ | Med-High | search, safety, FHIR, logic |
| 2 | Eval & Assurance | ★ | Medium | безопасную эволюцию |
| 4 | Governance | — | Medium | курацию, sync-recall |
| 5 | Provenance + Confidence | — | High | доверие, MVP-explainability |
| 7 | Offline + Sync + Freshness | — | High | деплой, **MVP** |
| 3 | Guideline Logic | — | Very High | клин-полноту (post-MVP) |
| 6 | Search | — | Med-High | usability |
| 8 | CDS Hooks + FHIR | — | High | EHR-embedding (postpone) |
| 9 | AI/Plugins/RAG | — | High | AI-фичи (postpone) |

## Dependency Graph (phase-level)
```
 v1 kernel (frozen) → [P0]★ → { [P1]★, [P2]★, [P4] }
 [P1] → [P6], [P3]  ;  DQ-B(STTR) → [P3]  ;  DQ-C(curation) → [P4]
 { [P1],[P3],[P4] } → [P5] → [P7] → MVP → [P8],[P9] (postpone)
 DQ-A → gated by [P2]
```

## Critical Path
`P0 → P1 → P2 → P4 → DQ-C(курация LEVEL A) → P5 → P7 → MVP → P3 (полнота)`.
**Разблокирует всё:** P0, P1. **Фундаменты:** P0, P1, P2. **Откладываемо:** P8, P9, полная P3, международность.

## Risk Matrix (топ)
| Риск | L | I | Митигация |
|---|---|---|---|
| Guideline-logic authoring bottleneck (P3) | High | High | пилот на единицах; coexist с flat |
| STTR-качество (DQ-B) | Med | High | metric-driven + P2 gate + review |
| Курация — узкое место (DQ-C) | High | High | RBAC-очереди; приоритет LEVEL A |
| Stale-but-recalled offline (P7) | Med | **Crit** | hard-expiry + forced-sync |
| Confidence-математика (P5) | Med | Med | отдельный design-раунд |
| AI ломает детерминизм (P9) | Med | High | determinism-contract |

## MVP (минимальный безопасный offline CDSS)
Ядро v1 + P0 + P1(ATC-safety) + P2(coverage) + P4-partial(gate) + DQ-C(LEVEL A→PRODUCTION_CURATED) + P5-partial(Evidence) + P7(packaging+Guard) + честный coverage. **Исключает:** полную Guideline Logic (P3), sync, FHIR, AI, semantic search.

## Production Readiness Checklist
- [ ] P0: ридеры за портами; hash/подпись; 0 regression.
- [ ] P1: allergy через ATC; coverage-report; safety green.
- [ ] P2: conformance + coverage(A/B/C) + baseline.
- [ ] DQ-C: LEVEL A курирован → PRODUCTION_CURATED; dedup; allergy верифицирован.
- [ ] P4: RBAC + separation-of-duties; промоция с подписями; аудит immutable/reversible.
- [ ] P5: per-recommendation Evidence + confidence; RFC H1 согласован; воспроизводимость.
- [ ] P7: packaging; forced-recall/expiry; last-synced.
- [ ] Production Guard: не стартует на не-curated (strict).
- [ ] Safety-инварианты (v1 конституция) тестируемы и green.
- [ ] Coverage-сигнал различим (нет данных / не покрыто / есть).
- [ ] Determinism-инвариант на реальном бандле.
