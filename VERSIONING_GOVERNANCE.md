# VERSIONING_GOVERNANCE.md
## Regimen Versioning, Change Detection & Diff · P5.2 · Phase 4
## Status: PROPOSED (design only)

> Extends `CLINICAL_REGIMEN_MODEL.md` §2.9 (version/superseded_by fields) and reuses kb_p44's
> existing append-only, conflict-triggers-new-version machinery (`KnowledgeBase.add_document`'s
> supersede-on-conflict logic, already certified 2026-07-15) — this document does not invent a new
> versioning mechanism, it specifies how it applies to `ClinicalRegimen`.

## 1. Regimen v1 → v2: what triggers a new version
A new version of a regimen (same clinical identity — same `(guideline_id, diagnosis/mkb,
drug_normalized, population, therapy_line)` grouping key from `REGIMEN_ASSEMBLY_ENGINE_RFC.md` §3
Stage A) is created when:
- The source guideline is updated (a new PDF/edition for the same `clinrec_id`) and re-extraction
  produces different constituent Knowledge Objects for the same clinical key.
- A previously `REVIEW_REQUIRED`/conflict-flagged regimen is re-resolved with different constituent
  facts (e.g. after a data-quality fix).
- A physician-initiated correction (`manual_override`, preserved from `normalized_regimens`'s schema
  per `CLINICAL_REGIMEN_MODEL.md` §2.7) changes a clinical field.

**What does NOT trigger a new version:** re-running assembly against an unchanged snapshot
(deterministic — produces the identical regimen, same `regimen_id`, no new version, per
`REGIMEN_ASSEMBLY_ENGINE_RFC.md` §4 determinism guarantee). Re-review without a content change
(e.g. a second physician approval cycle for policy reasons) updates review metadata, not the
regimen version.

## 2. Version identity
- `regimen_id` (deterministic hash of the clinical key) is **stable across versions** — it identifies
  "this clinical recommendation slot," not a specific content snapshot.
- `version` (int, monotonic) + `superseded_by` (regimen_id+version composite, or null) identify a
  specific content snapshot, mirroring kb_p44's existing `(id, version)` uniqueness constraint
  (already invariant-checked: `INV-10`, no duplicate `(id, version)` rows, certified clean at full
  scale).
- Only the highest `PUBLISHED` version for a given `regimen_id` is servable under
  `ValidationPolicy.STRICT` — older versions remain queryable (audit, `AUDIT` policy) but are never
  returned to a clinical recommendation request.

## 3. Change detection
Deterministic field-by-field diff between the previous `PUBLISHED` version and the new candidate
version, computed at assembly time (not manually) whenever a re-assembly produces a
same-clinical-key regimen with different content:
```
diff = {
  regimen_id, from_version, to_version,
  changed_fields: [ { field, old_value, new_value, old_source_object_id, new_source_object_id } ],
  unchanged_fields: [...],   # explicit, not just omitted — makes the diff complete, not partial
  reason: guideline_update | data_quality_fix | manual_override | conflict_reresolution,
  source: { guideline_id, pdf, page, ...new provenance },
  triggered_by: system | user_id (for manual_override),
  detected_at: timestamp
}
```
This `diff` record is itself an audit artifact (append-only), not a transient computation — it
answers "what changed and why" without needing to reconstruct it later from two raw regimen states.

## 4. Diff review requirement
A version change to an already-`PUBLISHED` regimen does NOT bypass the review lifecycle — the new
version re-enters at `ASSEMBLED` and proceeds through the same gates
(`CLINICAL_KNOWLEDGE_LIFECYCLE.md`). The diff record is presented to reviewers as primary review
material (per `REVIEW_WORKFLOW_RFC.md` §2.4, reviewers examine `assembly_trace`; for a re-version,
the diff is examined alongside it — "what specifically changed" is faster to review than
"re-review the whole regimen from scratch"). This is a review-efficiency mechanism, not a
review-skipping one.

## 5. Diff record schema (the exact fields the mandate requests)
| Field | Source |
|---|---|
| old recommendation | previous `PUBLISHED` `ClinicalRegimen` (full snapshot, retained per `SUPERSEDED` state) |
| new recommendation | candidate version's `ClinicalRegimen` |
| reason | `diff.reason` enum (§3) |
| source | `diff.source` (new provenance chain, `KNOWLEDGE_TO_REGIMEN_PIPELINE.md` §2) |
| reviewer | from the Clinical Review Ledger entry that approved this version (`REVIEW_WORKFLOW_RFC.md` §3) |
| timestamp | `diff.detected_at` (change detection) + separate `reviewed_at`/`published_at` (lifecycle transitions, distinct timestamps for distinct events — never collapsed into one "updated_at") |

## 6. Retention
`SUPERSEDED` and `DEPRECATED` regimens are never deleted (terminal states in
`CLINICAL_KNOWLEDGE_LIFECYCLE.md` §2, retained for audit). This is what makes
`KNOWLEDGE_AUDIT_MODEL.md`'s 5-year reproducibility question answerable: reconstructing "what did the
system recommend on date X" requires walking back through superseded versions by their
`published_at`/`superseded_at` timestamps, which are permanent, append-only facts.
