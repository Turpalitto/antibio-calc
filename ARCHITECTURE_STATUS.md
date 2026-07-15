# ARCHITECTURE_STATUS.md — ANTIBIO

## P5.6 architecture addendum — 2026-07-15

`Review Workbench` is an independent layer beside clinical validation tooling, downstream of immutable ClinicalRegimen/TherapeuticOption snapshots and explicitly disconnected from Clinical Decision Engine. Dedicated SQLite v1 stores immutable targets, mutable queue state with optimistic revision, and append-only events. No medical fact is edited in place; no auto approval exists.

**One-page reference. Single source of truth for architecture status.**

**Date:** 2026-07-10

## Architecture Version
- **v3 (Reference Architecture)** — FROZEN (accepted 2026-07-10)
- Base documents: `ARCHITECTURE_V3.md`, `ENGINEERING_MASTER_PLAN.md`, `DEVELOPMENT_BACKLOG.md`
- Changes to architecture ONLY via RFC for real engineering reason.

## Engineering Version
- **v1 kernel** — FROZEN
- Phase 0 (Knowledge Foundation) in progress

## Frozen Contracts (MUST NOT change without new RFC)
- Architecture v3
- BundleManifest (P0-1) + JSON Schema + validator API
- Extraction pipeline
- Medical Normalizer (models, parsers, dictionary, validator, db)
- SQLite schema
- Clinical Decision Engine v1 (10-stage pipeline, invariants, models)
- Version axes: schema_version, version, requires_kernel, bundle_format
- I10 Forward Compatibility (ignore unknown optional fields)
- Production Guard logic
- Determinism contract (P2)

## Open RFCs
- None (P0-1 CLOSED)

## Closed RFCs
- P0-1 BundleManifest Specification (CLOSED 2026-07-10)
- RFC H1 (per-recommendation Evidence) — CLOSED for v1 (recommendation to revisit in v1.1 if Flutter requires)

## Implementation Progress
- M1–M8: Clinical Decision Engine core — DONE
- M9: Audit remediation — DONE
- M10–M13: Data quality, governance infra, release readiness — DONE
- P0-1 to P0-4: **COMPLETE + FROZEN**. See P0_COMPLETION_REPORT.md. Locked.
- P1-A Drug Terminology: COMPLETE + FROZEN. P1-B Diagnosis Terminology: analysis done (exact, no synonyms/trace). Traceability + Optimization laws. Clinical focus.

## Current Critical Path
P0 (COMPLETE) → P1 (Terminology, RFC done) → P2 (Eval) per plan. Clinical value driver.

## Key Principles (v3)
- Ports & Adapters / Knowledge-as-Data
- Kernel frozen, variability in data/bundles
- Deterministic reasoning
- Safety as hard orthogonal gate
- Provenance to source
- Offline-first
- Curation as gate (DRAFT → CURATED → PRODUCTION)

## Status
All foundational architecture decisions locked. Execution phase active. No redesign. Implementation per backlog only.
