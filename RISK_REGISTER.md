# RISK_REGISTER.md
## P5.0 Knowledge Platform Migration — Risk Register · Phase 6
## Status: PROPOSED (documentation only)

> Every risk identified while designing this migration package, ranked High/Medium/Low. This
> register is scoped to the RC-019 migration; it references but does not duplicate
> `ROOT_CAUSE_REGISTER.md` (the project-wide register) — migration-specific risks not yet in that
> register should be added there as their own RC-0NN entries when this program moves to execution.

## High

**MR-1 — Granularity mismatch is harder than it looks.**
`Regimen` aggregates must be assembled from atomic `kb_p44` facts (Dose/Medication/Contraindication
etc. as separate objects) with no existing "this Dose belongs to this Regimen" relationship in the
current schema. Measured `CKY.tables=1.1%` means the atomic-fact side currently yields very few
table-derived facts to assemble from at all — most regimen assembly will initially depend on the
LLM pipeline's output, not P4.4's, inverting the SSOT RFC's stated preference for rule-based tables
where they work. **Mitigation:** Migration Phase 1's exit gate explicitly requires the schema
extension to be reviewed against `RecommendationCandidate`'s full field set for completeness before
Phase 2 begins — this risk is why that gate exists.

**MR-2 — Frozen spec field gaps are unknown until enumerated.**
This RFC package asserts `Regimen` must supply all 24 `RecommendationCandidate` fields but has not
enumerated, field-by-field, which ones the current `antibiotic_regimens`/`normalized_regimens`
schema already supplies cleanly versus which are approximated. `source_section` is already noted in
the frozen model as "v1: empty (SQLite lacks this column; future schema extension)" — i.e. the
CURRENT engine already tolerates one missing field; there may be others not yet surfaced. **Not
mitigated by this package** — Migration Phase 1 must do this enumeration before schema work starts.

**MR-3 — No measured performance baseline exists.**
Every RFC in this package marks the current `Engine.recommend()` latency as UNKNOWN. Committing to
"no regression" as an exit gate (Migration RFC Phase 4/5, Executive Summary Phase 9) without a
number to compare against is a real risk of the gate being unenforceable in practice. **Mitigation:**
the very first action in execution (before any other migration phase) should be measuring and
recording the current baseline — this is a measurement task, explicitly not covered by this
documentation-only package.

## Medium

**MR-4 — `medical_normalizer`'s "FROZEN" status interacts with governance ambiguously.**
`sqlite_reader.py`'s docstring calls `medical_normalizer.db.NormalizerDB` FROZEN, in the same sense
this project uses "frozen" for the Clinical Decision Engine. This package proposes reusing
`medical_normalizer`'s normalization *logic* as a library inside a new ingestion mapper — it is
**UNKNOWN** whether "frozen" here means "frozen interface, logic reusable" or "frozen entirely, no
new callers." This should be confirmed against whatever governance record declared it frozen (not
located in this pass) before Migration Phase 2 begins.

**MR-5 — Review/approval fields in `normalized_regimens.sqlite` may already carry real human
decisions.**
The schema has `review_status`, `reviewed_by`, `review_date`, `approved`, `manual_override`,
`manual_notes`. Whether these columns are POPULATED (real physician sign-off already recorded) is
**UNKNOWN** — not verified in this pass. If real approvals exist, the migration must preserve them
onto the canonical `Regimen` objects (a re-approval requirement would be a significant, avoidable
regression of clinical validation work already done). **Action:** this must be checked (read-only)
before Migration Phase 2's mapping design is finalized.

**MR-6 — RC-011 (substring dedup) compounds if the write path is extended before it's fixed.**
Adding `Regimen` as a new object type writes through the same `KnowledgeBase.add_document()` /
`_content_key`/`_get_by_key` path already flagged as RC-011 (LIKE-based substring dedup, false-merge
risk). A new, larger object type increases the surface area for this known issue. **Mitigation:**
RC-011 should be resolved (real indexed key, not substring match) before or during Migration Phase 1,
not deferred past it.

**MR-7 — Golden dataset does not yet exist at the scale needed to gate cutover.**
`GOLDEN_DATASET_SPECIFICATION.md` specifies ≥500 cases but only ~15-20 are authored so far (worked
examples in the spec, physician-verification pending per `CLINICAL_VALIDATION_FRAMEWORK.md`).
Migration Phase 4's "zero unexplained divergence on the full golden dataset" exit gate is only as
strong as the dataset's actual coverage at the time it is checked. **Mitigation:** dataset authoring
(physician-capacity-bound, per the Roadmap) should track in parallel with migration engineering, not
follow it.

**MR-8 — Deployment/traffic model is unverified.**
This package repeatedly marks "does production traffic exist / is the engine deployed as a live
service" as UNKNOWN. If the engine is not yet in production use, several risks above (MR-3
performance, shadow-traffic assumptions in Migration Phase 4) are lower-stakes than assumed; if it
is, they are higher-stakes. **Action:** confirm deployment status before finalizing the shadow-
validation design.

## Low

**MR-9 — `clinical_engine/corpus/provenance.py` duplication during the compatibility window.**
Running both provenance mechanisms (the existing corpus resolver and the canonical store's native
provenance) as a cross-check (Migration RFC §Compatibility strategy) is deliberate and low-risk, but
if the cross-check itself is never actually run (treated as optional and skipped under time
pressure), its value is lost silently. **Mitigation:** make the cross-check part of Phase 4's
exit-gate checklist, not an optional nice-to-have.

**MR-10 — RESOLVED during this pass (not a residual risk).**
Initial concern: a proposed new Port might collide with the existing `RegimenProviderAdapter`
import in `engine.py`. Deeper read of `sqlite_reader.py:133-149` resolved this fully: the Port
(`RegimenProvider`, a one-method `Protocol`) already exists, `RegimenProviderAdapter` is already its
concrete adapter around `SQLiteReader` (explicitly commented `"""P0-2: Thin adapter... No new
logic."""`). `CLINICAL_ENGINE_ADAPTER_RFC.md` and `QUERY_LAYER_RFC.md` were corrected in this same
pass to design the new component (`CanonicalStoreRegimenProvider`) as a sibling implementation of
the existing port, not a parallel abstraction. Recorded here as a worked example of why every claim
in this package should be spot-checked against the real code before execution — this session found
and fixed one internally, but others may remain (see MR-2).

---

## Risk summary table

| ID | Risk | Severity | Status |
|---|---|---|---|
| MR-1 | Granularity mismatch harder than assumed | High | Open — mitigated by Phase 1 gate design |
| MR-2 | Unenumerated frozen-spec field gaps | High | Open — requires Phase 1 enumeration work |
| MR-3 | No performance baseline | High | Open — requires measurement before execution |
| MR-4 | "Frozen" scope of medical_normalizer ambiguous | Medium | Open — requires governance confirmation |
| MR-5 | Possible unpreserved human approvals | Medium | Open — requires read-only DB check |
| MR-6 | RC-011 compounds with new object type | Medium | Open — sequencing dependency on RC-011 |
| MR-7 | Golden dataset incomplete for full-strength gating | Medium | Open — tracked against Roadmap physician capacity |
| MR-8 | Deployment/traffic model unverified | Medium | Open — requires confirmation |
| MR-9 | Cross-check could be silently skipped | Low | Open — process discipline, not technical |
| MR-10 | Possible naming/abstraction collision with `RegimenProviderAdapter` | Low | Open — requires deeper code read before execution |
