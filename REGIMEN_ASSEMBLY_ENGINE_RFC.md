# REGIMEN_ASSEMBLY_ENGINE_RFC.md
## RFC — Regimen Assembly Engine · ANTIBIO · P5.1
## Status: PROPOSED (design only — no code, no implementation)

> The deterministic layer that converts atomic `kb_p44` Knowledge Objects into `ClinicalRegimen`
> aggregates (`CLINICAL_REGIMEN_MODEL.md`), which the Clinical Engine Adapter
> (`CLINICAL_ENGINE_ADAPTER_RFC.md`) then projects to `RecommendationCandidate`. This is the missing
> layer P5.1 exists to design.

## 1. Position in the pipeline
```
kb_p44 atomic objects            Regimen Assembly Engine        Clinical Engine
(Dose, Medication,        ─────▶ (THIS RFC)             ─────▶  (frozen, via
 Contraindication,               deterministic                  RecommendationCandidate)
 Evidence, Diagnosis,            grouping + conflict
 Recommendation)                 resolution + validation
```
Assembly runs at INGESTION/BUILD time, not per request. Its output — versioned `ClinicalRegimen`
objects — is stored in the canonical store and read by the engine adapter. This keeps the engine's
per-request path fast and deterministic (it reads finished regimens, never assembles live).

## 2. Four non-negotiable properties (from the mandate)
- **Deterministic** — same input objects + same assembly ruleset version + same snapshot ⇒
  byte-identical `ClinicalRegimen` set. No wall-clock, no RNG, no dict-iteration-order dependence
  (sort keys explicit). This mirrors the engine's own determinism requirement and kb_p44's
  append-only model.
- **Explainable** — every assembled regimen carries an assembly trace: which atomic objects were
  grouped, by which grouping key, which conflict-resolution rule fired, which facts were rejected
  and why. The trace is data, not logs.
- **Reproducible** — assembly is a pure function of (snapshot of kb_p44, ruleset version). Re-running
  against an archived snapshot reproduces the exact regimens (supports audit/regulatory replay).
- **Versioned** — the assembly RULESET itself is versioned (`assembly_ruleset_version`), stored on
  every regimen, so a change in grouping/priority logic is distinguishable from a change in source
  data.

## 3. Assembly stages (deterministic pipeline)

### Stage A — Grouping (atomic facts → candidate regimen clusters)
Group kb_p44 objects into candidate regimens by the natural clinical key:
`(guideline_id, diagnosis/mkb, drug_normalized, population, therapy_line)`. Each cluster gathers the
Dose / route / frequency / duration / Contraindication / Evidence objects that share this key and
trace (via provenance) to the same guideline section/table. Grouping is deterministic: objects are
sorted by (guideline_id, page, table_row, table_col, object_id) before clustering.

### Stage B — Field resolution (cluster → regimen fields)
For each cluster, resolve each `ClinicalRegimen` field from its constituent objects:
- Single unambiguous fact → take it.
- Multiple facts for one field (e.g. two Dose objects) → **conflict**, resolve per §5.
- Missing required fact → the regimen is incomplete; it does NOT get a fabricated default — it is
  routed to the review/reject path (see Validation Gates RFC), never silently completed.
- Evidence / Contraindication facts linked to the same section attach as `evidence_level` /
  `contraindications` (net-new enrichment).

### Stage C — Alternatives linking
Within a (guideline_id, diagnosis, population) group, regimens differing only by drug and marked
non-first-line become `alternatives` links on the first-line regimen (and vice-versa). Deterministic:
sort by (therapy_line rank, drug_normalized).

### Stage D — Confidence & provenance assembly
- `confidence` = a deterministic function of constituent field confidences. Proposed: the **minimum**
  across required fields (weakest-link — a regimen is only as trustworthy as its least-certain
  clinical field), matching the "min() so the weakest link dominates" principle already adopted in
  `CLINICAL_VALIDATION_FRAMEWORK.md`'s confidence scoring. Per-field values retained in
  `field_confidence`.
- Provenance chain assembled per `KNOWLEDGE_TO_REGIMEN_PIPELINE.md` §provenance.

### Stage E — Versioning & id
- `regimen_id` = deterministic hash of the clinical key (Stage A key) — stable across rebuilds so a
  regimen keeps its identity when source data is unchanged (mirrors kb_p44's `_stable_id`).
- If a regimen with the same id but different content already exists (guideline update) → new
  `version`, previous marked `superseded_by` — reusing kb_p44's existing conflict/version machinery,
  not a new mechanism.

## 4. Determinism guarantees (explicit)
- All sorts use fully-specified keys (no ties left to insertion order).
- No timestamps in content-bearing fields (only in audit metadata, excluded from the id hash).
- The ruleset is a versioned, declarative table of grouping keys + priority rules, not imperative
  scattered logic — so a change is a data diff, reviewable and attributable.

## 5. Conflict resolution (design)
See `REGIMEN_VALIDATION_GATES.md` for the validation side; here is the resolution ORDER when two
sources disagree on a field (dose, duration, or drug choice):
1. **Guideline scope match** — a guideline whose diagnosis/population matches the regimen's context
   more specifically wins over a more general one (specificity beats generality).
2. **Guideline recency** — newer `guideline_year` (from diagnosis_index) wins, when both are the
   same КР lineage. (kb_p44 already models this as supersession.)
3. **Evidence rank** — higher УДД/УУР (from Evidence objects) wins.
4. **Confidence** — higher constituent-field confidence wins.
5. **Unresolved** → do NOT pick arbitrarily. Emit BOTH as sibling regimens flagged
   `validation_verdict=REVIEW` with an explicit conflict record (reusing kb_p44's `conflicts` table
   pattern), routed to human review. **Fail safe = surface the conflict, never silently merge or
   pick** — consistent with this project's governance ("no autonomous conflict resolution").

Worked examples:
- *Two guidelines, different dose, same recency/evidence* → both retained, REVIEW, conflict recorded.
- *Two guidelines, different duration, one newer* → newer wins (rule 2), older superseded, trace
  records the decision.
- *Two guidelines, different first-line antibiotic* → if scope/recency/evidence cannot break the
  tie, both surface as first-line alternatives with a REVIEW flag — a physician decides, not the
  assembler.

## 6. Explainability output (per regimen)
```
assembly_trace: {
  ruleset_version, snapshot_version,
  grouping_key: {...},
  constituent_object_ids: [...],           # every kb_p44 object that fed this regimen
  field_sources: { dose: obj_id, route: obj_id, ... },
  conflicts: [ { field, candidates:[...], rule_fired, outcome } ],
  rejected_facts: [ { obj_id, reason } ]
}
```
This makes the P5 Explainability API (from `docs/rfc/P5_KNOWLEDGE_PLATFORM_RFC.md`) able to answer
"why this dose?" all the way down to the PDF cell, with no heuristic gaps.

## 7. What this RFC does NOT do
- It does not change the engine, `RecommendationCandidate`, or the frozen spec.
- It does not run per-request (build-time only).
- It does not invent clinical facts — missing facts route to review/reject, never to a default.
- It does not decide pathogen sourcing (dependency, per the domain model).

---

## Final question — the 10-year certified-CDSS architecture

**If ANTIBIO must be a certified clinical decision support system used by physicians for 10 years,
the architecture I would choose is: a single, versioned, immutable Knowledge Object store
(kb_p44's provenance contract) as the source of truth, with a deterministic, ruleset-versioned
Regimen Assembly Engine as the ONLY path from atomic evidence to clinical regimens, and the Clinical
Decision Engine reading only assembled, human-approved regimens through a stable port.**

The load-bearing reasons, each grounded in what this project has already learned:

1. **Determinism and reproducibility are not features, they are certification prerequisites.** A
   CDSS a physician trusts for 10 years must be able to answer, for any recommendation ever made,
   "which guideline, which page, which cell, which rule, which version" — and reproduce it exactly
   from an archived snapshot. The assembly-at-build-time + immutable-versioned-store design makes
   this a property of the architecture, not something to be carefully maintained. The alternative
   (assemble live per request, or edit regimens in place) makes reproducibility a constant fight.

2. **The provenance contract must be the spine, not an add-on.** This project spent an entire cycle
   discovering (RC-012…018) that provenance bolted on after the fact silently loses information. A
   10-year system must have provenance as a first-class, invariant-enforced property from atomic
   fact through assembled regimen to served recommendation — which is exactly the chain
   `KNOWLEDGE_TO_REGIMEN_PIPELINE.md` specifies.

3. **Humans stay in the loop at the regimen boundary, not the fact boundary.** Physicians cannot
   review 24,705 atomic Dose objects; they can review assembled regimens. The assembly layer is
   where confidence, conflict, and evidence converge into a reviewable clinical unit — so the
   human-approval gate (`REGIMEN_VALIDATION_GATES.md`) sits there, and `approved` regimens are the
   only thing the engine serves. This is how the system stays both scalable and safe.

4. **Conflict is surfaced, never resolved autonomously.** Over 10 years, guidelines will disagree
   and update constantly. An architecture that silently picks a winner will eventually pick wrong
   and no one will know why. Surfacing conflicts as REVIEW-flagged sibling regimens with a recorded
   rule trace is slower but is the only defensible choice for a safety-critical system.

5. **Both extraction methods feed one model.** Do not bet the 10-year system on either the LLM
   pipeline or the rule-based pipeline exclusively — the measured evidence (CKY.tables=1.1% for
   rule-based on tables; 100% validated for LLM on regimens) says each is stronger on different
   content. Converge the MODEL (one `ClinicalRegimen` contract) and let ingestion use whichever
   extractor is more reliable per field, with provenance recording which one did.

The single most important architectural commitment: **the engine must never read anything a human
has not approved, and must never serve anything it cannot trace to a source.** Every other decision
in this package serves that one.
