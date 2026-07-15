# REVIEW_WORKFLOW_RFC.md
## Human Review System · P5.2 · Phase 2 (+ Phase 5 Conflict Governance)
## Status: PROPOSED (design only)

> **2026-07-15 implementation note:** the actual built system (`clinical_engine/review_workbench/`)
> now implements and, where it found real gaps, hardens this design. See
> `REVIEWER_IDENTITY_AND_ASSIGNMENT_POLICY.md`, `SECOND_REVIEW_BLINDING_SPEC.md`,
> `REVIEW_CONSENSUS_STATE_MODEL.md`, `MEDICAL_QA_SIGNOFF_SPEC.md`, and
> `P56_REVIEW_GOVERNANCE_HARDENING_REPORT.md` for the current, implemented, tested state model —
> which supersedes any conflicting detail below.

> Reuses the roles and verdict vocabulary already defined in `CLINICAL_VALIDATION_FRAMEWORK.md`
> §1/§2.3 — this document does not invent parallel names. It specifies how those roles operate the
> Clinical Review Queue for `ClinicalRegimen` objects (P5.1) moving through `REVIEW_REQUIRED`
> (`CLINICAL_KNOWLEDGE_LIFECYCLE.md`).

## 1. Roles (mapped, not reinvented)

| Mandate's role | Maps to (existing, `CLINICAL_VALIDATION_FRAMEWORK.md` §1) | Queue responsibility |
|---|---|---|
| Physician reviewer | **Reviewer A (Primary)** | First independent clinical review of a queued regimen |
| Second reviewer | **Reviewer B (Secondary)** | Second independent, blind review of the same regimen |
| Adjudicator | **Adjudicator** (senior/ID specialist, not A or B) | Resolves A↔B disagreement; final clinical word |
| Administrator | **Medical QA Lead** (assignment/routing authority) + delegated publication authority for routine cases (`CLINICAL_KNOWLEDGE_LIFECYCLE.md` §3) | Queue management: assignment, prioritization, escalation, non-clinical publication logistics |

**Independence rule (inherited, hard):** Reviewer A and B reach verdicts independently and blind to
each other. The Adjudicator is always a third person. (Verbatim rule from
`CLINICAL_VALIDATION_FRAMEWORK.md` §1, restated here because it governs the queue mechanics below.)

## 2. Clinical Review Queue — design

### 2.1 Queue entry
A `ClinicalRegimen` enters the queue when it transitions to `REVIEW_REQUIRED`
(`CLINICAL_KNOWLEDGE_LIFECYCLE.md` §3). Queue entry record:
`regimen_id, version, trigger_reason (conflict | mandatory-risk-axis | QA-override | low-confidence),
entered_at, priority`.

### 2.2 Priority (deterministic, not first-come-first-served)
Priority order, highest first:
1. **Safety-critical trigger** — Gate 3 safety check downgrade (dose-ceiling, pediatric-no-weight,
   unstructured pregnancy contraindication).
2. **Conflict** — Gate 4 unresolved multi-guideline conflict (§4 below).
3. **Hard-to-cover risk axis** — pregnancy+allergy, neonate+renal, or other combinations flagged in
   `GOLDEN_DATASET_SPECIFICATION.md` §6 as high-risk.
4. **Low confidence** — assembly `confidence` below a defined floor (value TBD at execution; this
   document specifies the mechanism, not the number, per STRICT MODE).
5. **QA Lead manual override** — routine escalation.
Deterministic tie-break: earliest `entered_at`.

### 2.3 Assignment
Medical QA Lead assigns Reviewer A and Reviewer B (both competent in the relevant specialty, per
`CLINICAL_VALIDATION_FRAMEWORK.md` §3's existing assignment rule — reused, not restated in full).

### 2.4 Review steps (per regimen, reusing CVF's per-assertion review mechanics)
Each reviewer independently examines: the assembled `ClinicalRegimen`, its `assembly_trace`
(P5.1 §6 — which objects, which fields, which conflicts), and the source provenance chain
(`KNOWLEDGE_TO_REGIMEN_PIPELINE.md` §2) down to the PDF/page/cell. Reviewer records a verdict using
the **existing verdict vocabulary** (`CLINICAL_VALIDATION_FRAMEWORK.md` §2.3, reused verbatim):
`ACCEPT · ACCEPT_WITH_NOTE · REJECT_FIDELITY · REJECT_CLINICAL · NEEDS_INFO · ABSTAIN`.

### 2.5 Approval rule
- Two independent `ACCEPT`/`ACCEPT_WITH_NOTE` (concordant) → `PHYSICIAN_APPROVED`.
- Any `REJECT_FIDELITY`/`REJECT_CLINICAL` from either reviewer → **not auto-rejected** — routes to
  Adjudicator (a single reviewer's reject is not final, mirroring the rule that a single ACCEPT is
  not final either — symmetry is intentional).
- `NEEDS_INFO` → routes back to the pipeline (provenance/normalization gap) — cannot be resolved by
  more review, must be resolved by better data (routes to `REJECTED` if the gap cannot be closed, or
  re-queued after a data fix).
- `ABSTAIN` → Medical QA Lead reassigns to a reviewer with matching specialty.
- Adjudicator's ruling on any disagreement is final and binding (no further escalation tier — matches
  `CLINICAL_VALIDATION_FRAMEWORK.md` §4).

### 2.6 Conflict handling within the queue (Phase 5 — multi-guideline conflict governance)
This is the human-facing complement to `REGIMEN_ASSEMBLY_ENGINE_RFC.md` §5's automated
conflict-resolution ORDER (specificity → recency → evidence → confidence). When the automated order
cannot resolve a conflict (both sibling regimens surface, per Assembly RFC rule 5), the queue
workflow is:

1. **Detect** — Gate 4 (`REGIMEN_VALIDATION_GATES.md`) flags the conflict at assembly time; both
   sibling `ClinicalRegimen`s enter `REVIEW_REQUIRED` together, cross-referenced.
2. **Store** — the conflict record (both regimen ids, the differing field(s), each one's
   provenance/evidence-level) is persisted append-only (mirrors `kb_p44`'s existing `conflicts`
   table pattern — reused, not redesigned).
3. **Route** — both siblings go to the SAME Reviewer A/B pair (not split across different
   reviewers) so the comparison is made by one consistent clinical judgment, then Adjudicator if A/B
   disagree on the resolution.
4. **Resolve** — the reviewer/adjudicator picks one of: (a) one regimen wins, other →
   `SUPERSEDED`-equivalent for conflict (a `REJECTED`-with-reason, distinct from a quality reject —
   tag `reason=SUPERSEDED_BY_CONFLICT_RESOLUTION`), (b) both are clinically valid alternatives (not
   truly conflicting — re-tag as `alternatives`, both proceed to `PHYSICIAN_APPROVED` linked per
   `CLINICAL_REGIMEN_MODEL.md` §2.5), (c) neither is acceptable as stated → both `REJECTED`, escalate
   to re-extraction/re-assembly.
5. **Document** — the decision, its rationale, and the deciding human are recorded on BOTH regimen
   records (even the rejected one) — this is the artifact `KNOWLEDGE_AUDIT_MODEL.md` §Phase 6 needs
   to answer "why NOT drug Y" five years later, not just "why drug X."

Worked example (from the mandate): Guideline A says drug X, Guideline B says drug Y, for the same
diagnosis/population, and Assembly RFC's automated rules (specificity/recency/evidence/confidence)
do not break the tie. Both `ClinicalRegimen`s enter the queue tagged `conflict_group_id`. The
assigned reviewer pair examines both source guidelines directly (not just the assembled summary),
reaches outcome (a), (b), or (c) above, and the decision + rationale is written to both records.

## 3. Audit trail
Every queue action (assignment, verdict, adjudication, publication decision) is an append-only
**Clinical Review Ledger** entry, extending the existing ledger already specified in
`CLINICAL_VALIDATION_FRAMEWORK.md` §2.4 (`assertion_id, ko_version, guideline_id, reviewer_id,
specialty, verdict, confidence, rationale, reviewed_at, source_ref`) to the regimen level: add
`regimen_id, regimen_version, conflict_group_id (nullable), lifecycle_transition
(from_state→to_state)`. Nothing is ever deleted or overwritten — corrections are new ledger entries,
not edits (same append-only discipline as `kb_p44`'s object versioning).
