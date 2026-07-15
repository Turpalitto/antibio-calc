# PROVENANCE_CERTIFICATION.md
## Provenance Layer — Production Certification · ANTIBIO
## Status: **CERTIFIED — PRODUCTION READY** (2026-07-15, full-scale measured)

> Final certification of the provenance layer. Answers one question with evidence:
> **"Can every Knowledge Object be traced to its exact origin — pdf, page, guideline, engine, table
> cell, original wording — without heuristics, without ambiguity, without information loss?"**
> Certification is granted ONLY if all gates below are measured PASS on the full corpus KB. No new
> code changes are made during certification (code freeze, DECISIONS 2026-07-14); failing gates
> open a Root Cause Program, they are not patched mid-audit.

## 1. Requirements (from PROVENANCE_SPECIFICATION.md)
Canonical vocabulary = `Provenance` field names; producer emits, consumer maps 1:1, no inference;
original wording never discarded; guideline_id present; engine/table_conf real; versioned schema;
backward compatible; no silent information loss on merge.

## 2. Defects found & resolved (this contract cycle)
| ID | Defect | Severity | Status | Evidence |
|----|--------|----------|--------|----------|
| RC-012 | original_text lost (raw≠text) | High | Fixed | 1-PDF + live rebuild: original_text 100% |
| RC-013 | guideline_id/paragraph never produced | High | Fixed | guideline_id 100% (paragraph O) |
| RC-014 | engine inferred; table_conf dropped | Med | Fixed | canonical keys; table_conf captured |
| RC-015 | dead `semantic` column | Low | Documented-dead | schema note |
| RC-016 | RapidTable fallback API drift | Med | Fixed | adapter; fallback functional |
| RC-017 | merge collapsed distinct cells (data loss) | High | Fixed | probe: both cells kept; regression test |
| RC-018 | v1 schema_version not backfilled | Low | Fixed | v1 rows → schema_version=1 |

## 3. Verification performed
- Reusable stage tracer (`diagnose_pipeline.py`), invariant checker (`knowledge_invariants.py`),
  coverage (`knowledge_coverage.py`), yield/CKY (`semantic_yield_audit.py`).
- Independent Auditor pass (adversarial disprove) — found RC-017/018, fixed, re-audited clean.
- Backward compat on a real v1 DB (48617 prov rows) — opens, migrates, readable.

## 4. Measured results — FINAL (192/192 PDFs, 100,854 provenance rows, 31,336 objects)
| Gate | Target | Measured | Verdict |
|------|--------|----------|---------|
| Rebuild complete | 192/192 PDFs | 192/192, 0 tracebacks | **PASS** |
| Provenance: original_text populated | 100% | 100% (0 NULL of 100,854) | **PASS** |
| Provenance: guideline_id populated (known guidelines) | 100% | 100% (192/192 distinct PDFs mapped) | **PASS** |
| Provenance: table_row ⇒ table_conf (INV-17) | 0 violations | 0 violations | **PASS** |
| Invariants: blocking failures | 0 | 0 (INV-01/02/03/08/09/10/12 all PASS) | **PASS** |
| INV-09 (original wording) | PASS | 0 violations (was 1,442 pre-fix) | **PASS** |
| Silent nulls (extractor/engine/schema_version) | 0 | 0 across all five fields | **PASS** |
| RC-017 (distinct table cells retained) | 0 collapses | 0 same-page multi-cell collapses; regression test green | **PASS** |
| RapidTable fallback functional (RC-016) | live | 15 provenance rows via `layout_engine='rapidtable'` | **PASS** |
| Regression suite | green | 72 passed, 1 xfailed, 0 failed | **PASS** |
| CKY baseline captured | yes | `CKY.overall=10.3%`, per-axis + per-source (`pr008_yield_FINAL.json`) | **PASS** |
| Coverage baseline captured | yes | full per-dimension report (`coverage_FINAL.json`) | **PASS** |

## 5. Certification decision — **CERTIFIED, 2026-07-15**
**Release Readiness Review, Board final verdict.** All twelve gates in §4 measured PASS on the
complete 192-PDF corpus (31,336 objects, 100,854 provenance rows). No code changes were made during
this final audit (freeze respected).

**Answer to the founding question:** *"Can every Knowledge Object be traced to its exact origin —
pdf, page, guideline, engine, table cell, original wording — without heuristics, without ambiguity,
without information loss?"* — **YES, for the Knowledge Base itself**, evidenced by: 100% non-null
original_text/guideline_id/extractor/layout_engine/semantic_engine across 100,854 rows; 0 blocking
invariant violations; 0 measured cell-level provenance collapses (RC-017 held at scale); the
consumer maps provenance 1:1 from canonical producer keys with no inference (per
`PROVENANCE_SPECIFICATION.md`).

**Scope caveat (not a certification failure, but load-bearing):** this YES applies to `kb_p44.db`.
It does **not** yet extend to what a physician or patient actually receives, because the Clinical
Decision Engine reads a separate, disconnected data source (RC-019, `ENTERPRISE_ARCHITECTURE_REVIEW.md`
EAR-1). The Provenance Layer as built is production-ready; wiring it to the serving layer is P5/P6
work, tracked and not silently dropped.

**Provenance Layer is certified PRODUCTION READY.**
