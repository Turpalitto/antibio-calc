# ANTIBIO — Development Backlog

## Active P5.6 blockers — 2026-07-15

1. BLOCKING/OWNER: revoke and rotate exposed provider credentials.
2. BLOCKING/OWNER: recover canonical source/docs/tests into Git; validate fresh clone.
3. P6 gate: complete real physician pilot cases in Review Workbench.
4. P6 gate: establish physician-approved population and pass Golden against approved data.
5. WARNING: optimize metrics summary only after review workload produces real usage data.

> **Статус:** ПРИНЯТО (2026-07-10). Строго по `ARCHITECTURE_V3.md` + `ENGINEERING_MASTER_PLAN.md`.
> Задачи мелкие и независимые (по одной, без крупных рефакторингов). Легенда: сложность **S/M/L/XL**, приоритет **Crit/High/Med/Low**.
> **Стандартный workflow каждого Issue:** Design → Review → Implementation → Tests → Code Review → Documentation → Merge.

## P0 — COMPLETE + FROZEN (2026-07-10)

See P0_COMPLETION_REPORT.md. Process building complete. No new rules.

## M1 — Phase 1: Terminology Binding *(split per roadmap)*
- P1-A Drug Terminology: COMPLETE + FROZEN (RFC + impl + Golden + benefit test).
- P1-B Diagnosis Terminology: analysis done (exact match only, no synonyms/trace, 101 conflicts).
- Traceability + Optimization laws.
- See P1-B_Diagnosis_Terminology_Analysis.md.
- P1-B next. Additive. All P0 frozen. No benefit = no change.

## M2 — Phase 2: Eval & Assurance *(foundation)*
- **[P2-1] Conformance-validator** — M/Crit. COMPLETE + FROZEN (additive, 2026-07-11). ConformanceValidator + opt-in loader + tests. Real green. RFC/Analysis. DoD met.
- **[P2-2] Coverage-метрики (A/B/C runtime)** — M/High. Deps: P0-4. DoD: воспроизводит 58/233/3; per-guideline level.
- **[P2-3] Regression-baseline harness** — M/High. Deps: P0-4. DoD: PASS/REVIEW/REJECT baseline + comparator.
- **[P2-4] Golden-runner в eval + CI** — S/Med. Deps: golden runner. DoD: прогон в pipeline.
- **[P2-5] Единый metrics-report** — S/Med. Deps: P2-1..4. DoD: один отчёт.

## M4 — Phase 4: Governance
- **[P4-1] Event-sourced audit-ledger** — M/High. Deps: M11-tooling. DoD: immutable/reversible; curation-тесты green.
- **[P4-2] RBAC + separation-of-duties** — M/High. Deps: P4-1. DoD: author≠approver.
- **[P4-3] Promotion-gate + подписи** — M/Crit. Deps: P4-2,P0-3. DoD: без подписей промоция блокируется; Production Guard уважает.
- **[P4-4] STTR-ingestion queue** — M/Med. Deps: P4-1. DoD: STTR-выход → DRAFT-бандл в review.

## M5 — Phase 5: Provenance + Confidence
- **[P5-0] Re-open RFC H1 (решение)** — S/Crit *(gate)*. Deps: —. DoD: одобренный scope model-change.
- **[P5-1] Per-recommendation Evidence** — L/High. Deps: P5-0,P0-4. DoD: Evidence на рекомендацию; invariants green.
- **[P5-2] Provenance-chain** — M/High. Deps: P0-3,P5-1. DoD: rec→bundle-hash→source→signature; верифицируема.
- **[P5-3] Confidence §7.3** — L/Med. Deps: P5-1. DoD: композиция + breakdown; детерминировано.
- **[P5-4] AI-content provenance** — S/Med. Deps: P5-2. DoD: атрибуция STTR-контента.

## M6 — Phase 6: Search
- **[P6-1] Embedded vector-index (LanceDB-класс)** — M/Med. Deps: P1-1. DoD: offline; детерминировано при версии индекса.
- **[P6-2] Terminology-bound matching + candidates** — M/High. Deps: P1-3,P6-1. DoD: «риносинусит»→«синусит»; никогда silent NO_MATCH.
- **[P6-3] Инвариант «search не назначает терапию»** — S/High. Deps: P6-2. DoD: тест.

## M7 — Phase 7: Offline + Sync + Freshness *(MVP-gate)*
- **[P7-1] Packaging + signing** — M/Crit. Deps: P0-1,P0-3. DoD: подпись верифицируется.
- **[P7-2] Sync-engine (atomic swap)** — L/High. Deps: P7-1. DoD: fetch+verify+swap; delta.
- **[P7-3] Safety-freshness (expiry/forced-recall/last-synced)** — M/Crit. Deps: P7-2,P4-3. DoD: отозванный safety блокируется offline; last-synced в выдаче.
- **[P7-4] Static-bundle fallback** — S/Med. Deps: P7-1. DoD: offline без sync = текущее поведение.

## M3 — Phase 3: Guideline Logic *(post-MVP)*
- **[P3-1] Схема decision-network (данные)** — L/High. Deps: P1-1. DoD: схема + пример-1638.
- **[P3-2] Criteria-evaluator + порт** — XL/High. Deps: P3-1,P1. DoD: критерии против patient+terminology; flat не затронут.
- **[P3-3] Coexistence-флаг (logic opt-in)** — M/High. Deps: P3-2. DoD: оба пути green.
- **[P3-4] Пилот 1638 + golden** — M/Med. Deps: P3-3,DQ-B. DoD: аллергия/рецидив по КР; golden PASS.

## M8 — Phase 8: Integration *(postpone)*
- **[P8-1] CDS Hooks inbound** — L/Low. Deps: P1,P5.
- **[P8-2] FHIR outbound adapter** — L/Low. Deps: P1,P5.

## M9 — Phase 9: AI/Plugins/RAG *(postpone)*
- **[P9-1] Deterministic-plugin contract** — M/Low. Deps: P5-2.
- **[P9-2] RAG grounding (explanation-only)** — L/Low. Deps: P5,P6.
- **[P9-3] GraphRAG explanation-адаптер** — L/Low. Deps: P9-2.

## M-DQ — Data/Content track *(параллельно, гейтит production)*
> ⚠️ DQ-A/B трогают FROZEN модули или новый STTR-проект → отдельное un-freeze/старт-решение.
- **[DQ-A]** Re-normalization Phase A. Gate: P2.
- **[DQ-B]** STTR. Питает P3-1/P4-4.
- **[DQ-C]** Врачебная курация LEVEL A. Gate: P4-3. (Человеческая задача.)

---

## Dependency Graph (issue-level)
```
v1 kernel(frozen) → P0-1 → {P0-2→P0-5, P0-3} → P0-4
 P0-1 → P2-1 ;  P0-4 → {P2-2, P2-3}
 P0-2 → P1-1 → {P1-2(safety), P1-3→P6-2→P6-3, P1-4, P1-5, P3-1→P3-2→P3-3→P3-4}
 P6-1 → P6-2
 M11 → P4-1 → P4-2 → P4-3 → P4-4 ;  DQ-B→P4-4 ; DQ-C(curation)→P4-3
 P5-0 → P5-1 → P5-2 → {P5-3, P5-4}
 {P0-1,P0-3} → P7-1 → P7-2 → P7-3(←P4-3) ; P7-1→P7-4
 → MVP → {P8-*, P9-*} (postpone)
 DQ-A gated by P2
```

## Critical Path
`P0-1 → P0-2 → P0-3 → P0-4 → P1-1 → P1-2 → P2-1 → P2-2/P2-3 → P4-1 → P4-2 → P4-3 → DQ-C → P5-0 → P5-1 → P5-2 → P7-1 → P7-3 → MVP → P3-1→P3-2→P3-3`.

**Рекомендованная очередь первого спринта:** `P0-1 → P0-2 → P0-5 → P0-3 → P0-4 → P2-1 → P2-2 → P1-1 → P1-2 → P2-3`.
