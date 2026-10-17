# P2-2 Coverage Metrics (A/B/C runtime) — Analysis (ONLY)

**Date:** 2026-07-11
**Status:** Analysis ONLY. No RFC, no impl, no code.
**Workflow:** Per autonomous instruction: after P2-1 complete, onboard next (P2-2), perform ONLY Analysis, produce doc, update roadmap, STOP.

## Current State (repo truth only)

From DEVELOPMENT_BACKLOG:
- [P2-2] Coverage-метрики (A/B/C runtime) — M/High. Deps: P0-4. DoD: воспроизводит 58/233/3; per-guideline level.

From dataset_pruning_report.md (measured):
- LEVEL A: 58 guidelines, 1039 regimens (full PASS)
- LEVEL B: 233 guidelines (incomplete)
- LEVEL C: 3 guidelines (no abx)
- Total ~294 guidelines, 2675 regimens.

From ARCHITECTURE_V3:
- Evaluation & Assurance layer: golden + coverage(A/B/C) + drift + faithfulness.
- Δ4: Coverage / Negative-Knowledge — A/B/C в рантайме; «нет данных» vs «не покрыто».

From clinical_engine/tools/:
- performance_audit.py, clinical_data_audit.py mention per-guideline.
- No runtime A/B/C metric exposed in Engine or RecommendationSet.

From code inspection (no changes):
- Engine returns RecommendationSet with accepted/excluded per query.
- No built-in coverage report per guideline_id or A/B/C classification at runtime.
- diagnosis_index + sqlite + bundles provide data, but no aggregated coverage metrics API.
- Tests/test_curation etc have per-guideline but static.
- Golden runner focuses on case PASS/FAIL, not aggregate coverage.

P2-1 (conformance) separate (bundle level). P0-4 bundles enable data loading.

## Gaps (repo evidence)

1. Static reports (pruning_report) exist, but no runtime equivalent reproducible from Engine + bundles.
2. No per-guideline coverage level (A/B/C) in public models or trace.
3. No metric that "воспроизводит 58/233/3" from live config/data.
4. Negative-knowledge ("not covered") not distinguished in current output.
5. Per-guideline level needed for P2 eval harness.

## Analysis (derived)

P2-2 fits Evaluation layer (post P0-4 bundles, P2-1 conformance).
Additive: new metrics module or in engine metadata / RecommendationSet.
- Runtime function or Engine method: compute_coverage(guideline_ids or all) -> dict with A/B/C counts + per-gid level.
- Reproduce exact 58/233/3 from data (using verdict or data completeness).
- Per-guideline: attach to traces or separate report.
- Use bundles for data source (P0-4).
- Tests: assert reproduces known baseline.
- No change to clinical recs, no frozen, no P1.
- Clinical benefit: enables drift detection, assurance that key guidelines (A) are covered at runtime.

Proposed (analysis only): 
- clinical_engine/metrics.py or in pipeline: CoverageMetrics, compute_a_b_c(...)
- Integrate optional in Engine.
- Golden-like: baseline reproduction test.
- CI: fail if coverage drops.

Laws: Optimization (measurable eval improves quality), Traceability (per-gid).

No impl. This is Analysis.

## Handoff Notes
- Read DEVELOPMENT_BACKLOG, ARCHITECTURE_V3, dataset_pruning_report.md, P2-1 for context.
- Deps P0-4.
- Next after P2-1.
- ONLY analysis done. Do not implement.

**Analysis for P2-2 complete. STOP (per instruction: analysis only for next).**