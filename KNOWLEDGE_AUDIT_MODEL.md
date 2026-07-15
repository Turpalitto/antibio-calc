# KNOWLEDGE_AUDIT_MODEL.md
## Clinical Auditability — the 5-Year Reproducibility Question · P5.2 · Phase 6
## Status: PROPOSED (design only)

> Directly answers the mandate's question: *"Can we reproduce 'why did the system recommend this
> antibiotic?' after 5 years?"* Extends `KNOWLEDGE_TO_REGIMEN_PIPELINE.md` §2 (the provenance chain)
> with the versioning/review artifacts from `VERSIONING_GOVERNANCE.md` and `REVIEW_WORKFLOW_RFC.md`
> that a 5-year-old recommendation additionally needs.

## 1. The required chain (from the mandate)
```
Recommendation
  ↓
Regimen version
  ↓
Knowledge Object
  ↓
PDF
  ↓
Page
  ↓
Table/Text
```

## 2. Answer: YES, conditionally — and here is exactly what makes it true or false

**YES, if and only if every link below is retained and none is ever destructively overwritten.**
This document specifies what must be true; it does not itself guarantee it will remain true forever
— that is an operational commitment (retention policy), stated explicitly in §5.

| Link | What answers it | Already exists / new |
|---|---|---|
| Recommendation → Regimen version | The served `RecommendationCandidate.regimen_id` (engine already carries this on every candidate, per `CLINICAL_ENGINE_ADAPTER_RFC.md` §1) + the `version` that was `PUBLISHED` at the time the recommendation was served | **Partially new** — the engine has `regimen_id` today; recording WHICH VERSION was live at request time requires the engine (or a request-logging layer) to record `snapshot_version` per request. **Not designed here** (a P7 observability concern) — flagged as a dependency, not assumed solved. |
| Regimen version → Knowledge Object | `assembly_trace.field_sources` (`REGIMEN_ASSEMBLY_ENGINE_RFC.md` §6) — every field names its source object id, permanently, on the retained regimen version | **New (P5.1 design), not yet built** |
| Knowledge Object → PDF/page | kb_p44 `Provenance.pdf` + `.page` | **Exists, certified** (2026-07-15, 0 nulls at full scale) |
| Page → Table/Text | kb_p44 `Provenance.table_row/table_col/table_conf` (table-derived) or the flat-text extraction position (free-text derived) | **Exists, certified** (INV-17, 0 violations) |

## 3. What a 5-year-later audit request looks like
```
Given: a recommendation served on 2026-07-15 for patient context X, resulting in drug Y.
Reconstruct: why drug Y?

1. Look up the served regimen_id + snapshot_version from request logs (§2, dependency).
2. Retrieve that EXACT regimen version (never deleted — VERSIONING_GOVERNANCE.md §6 retention).
   If it has since been SUPERSEDED, the historical version is still queryable (AUDIT policy).
3. Read its assembly_trace: which kb_p44 objects, which assembly ruleset_version, which conflicts
   were resolved and how (REGIMEN_ASSEMBLY_ENGINE_RFC.md §6).
4. For each constituent object, read its Provenance: exact pdf, page, table cell (if applicable),
   original_text (never discarded, per PROVENANCE_SPECIFICATION.md).
5. If the regimen went through REVIEW_REQUIRED: retrieve the Clinical Review Ledger entries
   (REVIEW_WORKFLOW_RFC.md §3) — who reviewed, their verdict, their rationale, timestamped.
6. If a conflict was resolved: retrieve the conflict record + documented resolution
   (REVIEW_WORKFLOW_RFC.md §2.6 step 5) — including why the ALTERNATIVE drug was not chosen.

Result: a complete, human-readable chain from "drug Y, dose Z" back to the specific page and table
cell of the specific PDF, the specific reviewer who approved it, and — if relevant — the specific
reason a competing guideline's answer was not used.
```

## 4. Reproducibility, not just traceability
The mandate asks to **reproduce**, not just trace. Two distinct guarantees:
- **Traceability** (§3 above): explain a past recommendation from retained records.
- **Reproducibility**: re-run the ENTIRE pipeline (extraction → assembly → validation) against an
  archived snapshot and get the byte-identical regimen back. This requires:
  - The exact `snapshot_version` of kb_p44 at that time is itself immutable/archived (not just the
    live DB's current state) — a backup/archival policy, not designed here (dependency).
  - The exact `assembly_ruleset_version` is version-controlled (the ruleset is data, per
    `REGIMEN_ASSEMBLY_ENGINE_RFC.md` §4 — "a versioned, declarative table," which implies it can be
    checked into version control like code, trivially archivable).
  - Determinism holds (already a hard requirement, `REGIMEN_ASSEMBLY_ENGINE_RFC.md` §2).
Reproducibility is the stronger, more valuable guarantee for a certified CDSS (it proves the system,
not just narrates a record) — and is achievable by this design PROVIDED the archival/backup
dependency (§5) is honored operationally.

## 5. Dependencies this document does not resolve (honest, not designed here)
- **Snapshot archival policy**: how long are old `snapshot_version`s of kb_p44 retained, and where
  (this is infrastructure/ops, P7 scope).
- **Request-level logging**: which `snapshot_version` served which specific recommendation — needed
  for the "Recommendation → Regimen version" link when multiple versions could theoretically be
  `PUBLISHED` in different snapshot windows. **This is the one genuine gap in the chain today** —
  flagged prominently, not glossed over.
- **Ruleset version control**: assumed to live in the same repository discipline as everything else
  in this project (git history) — reasonable given this project's practices, not independently
  verified as a formal requirement anywhere.

## 6. What must NEVER happen (the failure modes this design prevents)
- A `ClinicalRegimen` version being edited in place (breaks §3 step 2 — always append a new version,
  per `VERSIONING_GOVERNANCE.md`).
- An `assembly_trace` or `Provenance` field being backfilled/corrected without a new version (breaks
  reproducibility — a "fix" to historical data must be a new version, with the fix itself audited).
- A review verdict being overwritten rather than appended (breaks §3 step 5 — the Clinical Review
  Ledger is append-only by design, inherited from `CLINICAL_VALIDATION_FRAMEWORK.md`).
- A conflict resolution being recorded on only the winning regimen (breaks "why NOT drug Y" —
  `REVIEW_WORKFLOW_RFC.md` §2.6 step 5 requires documentation on BOTH regimens).

These are exactly the class of defect this project's own history has already demonstrated the cost
of (RC-001 silent data loss, RC-017 silent provenance collapse) — the audit model's job is to make
the *append-only, never-silently-lose-information* discipline structural for the review/versioning
layer, the same way it is now structural for the provenance layer.
