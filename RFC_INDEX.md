# RFC_INDEX.md — ANTIBIO

**List of all RFCs with status. Single source of truth.**

**Date:** 2026-08-01

## Status Legend
- **Draft** — Under discussion
- **Accepted** — Approved, ready for implementation
- **Frozen** — Implementation complete + Acceptance Review passed + contract locked
- **Implemented** — Code done (but not yet frozen)
- **Closed** — Fully done, backlog item resolved

## RFCs

| RFC | Title | Status | Date | Notes |
|-----|-------|--------|------|-------|
| **P0-1** | BundleManifest Specification | **Closed + Frozen** | 2026-07-10 | Schema + validator + I10. All 6 acceptance tests added. No further changes without new RFC. |
| P0-2 | Provider Ports (Regimen/Diagnosis/DrugSafety) | Accepted + Implemented | 2026-07-10 | RFC + adapters (Regimen/DrugSafety/Diag) + flag + DI update + stage mig + equality test. Legacy+providers coexist. 100% wrap. |
| P0-3 | Bundle Loader (infra) | Implemented + Tests + Frozen | 2026-07-10 | Analysis + RFC + loader (generic, registry, compat+hash) + pure infra tests. No medical. Frozen. |
| P0-4 | Bundle Wrapping | COMPLETE (checklist) | 2026-07-10 | Real hashes, loader smoke, flag. Migration done. See P0-4_Checklist.md. |
| P1 | Terminology Binding | P1-A FROZEN, P1-B CLOSED (ACCEPTED + FROZEN) | 2026-07-11 | P1-B: genuine PASS post review. 4 findings repro TRUE then fixed minimal. 0 fail pytest (relevant), Golden PASS, no reg, neg proves exclusion via gid. See P1-B RFC. P1-B FROZEN.

**P0 MILESTONE COMPLETE + FROZEN (2026-07-10).** See P0_COMPLETION_REPORT.md. All P0 contracts locked.
| P2-1 | Conformance Validator | CLOSED + FROZEN | 2026-07-11 | not_guideline_id + trace_code. Negative Golden now prove exclusion. Review PASS.
| P3 | Clinical Data Curation | In progress | 2026-07-11 | Medical data only. 101 conflicts, renal structure, synonyms x10, ATC, 300+ Golden. No engine touch.
| PERSONAL-PHYSICIAN | Local Personal Physician Decision-Support Mode | **Draft** | 2026-08-01 | Explicit local opt-in; default calculator and production governance unchanged. Requires owner acceptance before implementation. |
| H1 | Per-recommendation Evidence / Trace (§7.5) | Closed for v1 | 2026-07-10 | Recommendation: revisit in v1.1 if Flutter requires per-rec Evidence. |
| (Future) | — | — | — | — |

**Rule:** Any change to a Frozen contract requires a new RFC.

**P0 COMPLETE + FROZEN.**

**Current active:** P1-B Diagnosis Terminology (P1-A FROZEN). Analysis done. RFC next. Clinical value primary. See P1-B_Diagnosis_Terminology_Analysis.md. Additive, compat.
