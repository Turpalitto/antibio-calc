# REGIMEN_APPROVAL_MODEL.md
## Certification Model — Readiness Gates Before Production · P5.2 · Phase 7
## Status: PROPOSED (design only)

> The final gate a `ClinicalRegimen` passes before `PUBLISHED`
> (`CLINICAL_KNOWLEDGE_LIFECYCLE.md` §2). Resolves two items other P5.2 documents deferred here:
> the **fast-path policy** question (`CLINICAL_KNOWLEDGE_LIFECYCLE.md` §5 note) and the
> **interaction-check waiver** question (`CLINICAL_SAFETY_GATES.md` check 7).

## 1. Three gate categories (per the mandate)

### 1.1 Technical gates
| Gate | Requirement | Source |
|---|---|---|
| T1 | All 9 `CLINICAL_SAFETY_GATES.md` checks resolved to PASS or an explicit, recorded waiver (never silently skipped) | Safety Gates doc |
| T2 | Provenance chain complete (`INV-18`) — every field traces to a real, provenance-complete kb_p44 object | Validation Gates RFC |
| T3 | `snapshot_version` + `assembly_ruleset_version` recorded (reproducibility anchors) | Assembly Engine RFC §4 |
| T4 | If this is a new version of an existing regimen: `diff` record complete (`VERSIONING_GOVERNANCE.md` §3) | Versioning Governance |
| T5 | Determinism check: re-running assembly against the same snapshot reproduces the identical regimen (spot-checked, not necessarily re-run for every publication — a sampling policy, execution detail) | Assembly Engine RFC §2 |

### 1.2 Medical gates
| Gate | Requirement | Source |
|---|---|---|
| M1 | Two independent, concordant `ACCEPT`/`ACCEPT_WITH_NOTE` verdicts (Reviewer A + B), or Adjudicator ruling on disagreement | Review Workflow RFC §2.5 |
| M2 | If flagged by a mandatory-review trigger (high-risk axis, conflict, low confidence): review completed, not bypassed | Lifecycle §2 `REVIEW_REQUIRED` entry conditions |
| M3 | If part of a multi-guideline conflict: resolution documented on both sibling regimens (not just the winner) | Review Workflow RFC §2.6 step 5 |
| M4 | `reviewed_by` + `review_date` non-empty (`INV-21`) | Validation Gates RFC |

### 1.3 Governance gates
| Gate | Requirement | Source |
|---|---|---|
| G1 | Frozen Clinical Decision Engine spec compatibility — the regimen's fields satisfy `RecommendationCandidate`'s required set (`INV-19`) | Validation Gates RFC |
| G2 | No open, undocumented waiver (every waived check has a named approver + rationale — see §3) | This document |
| G3 | Sign-off Authority (or delegated Administrator, for routine non-flagged cases, §2 below) has recorded the publication decision | This document |
| G4 | Clinical Governance non-negotiables satisfied (no hallucinated fields, source hierarchy respected — inherited from `docs/governance/CLINICAL_GOVERNANCE.md`, referenced not restated) | Clinical Governance (existing) |

**Publication requires ALL of T1-T5, M1-M4, G1-G4.** Any single failing gate blocks `PUBLISHED` —
no category can compensate for another (a perfect technical score does not excuse a missing medical
review; a physician approval does not excuse a broken provenance chain).

## 2. Fast-path policy (resolves the open question from `CLINICAL_KNOWLEDGE_LIFECYCLE.md` §5)
The direct `VALIDATED → PHYSICIAN_APPROVED` edge (skipping the review queue) is **disabled by default
policy**. It may only be enabled for a narrowly-scoped class of regimens, and only by a governance
decision recorded exactly like a waiver (§3): the Sign-off Authority must explicitly define which
regimen class qualifies (e.g. "a re-published regimen whose `diff` shows zero changed clinical
fields versus its already-approved predecessor" — a genuine no-new-risk case), document the
rationale, and this scope is itself auditable. Absent such a recorded decision, **every regimen
passes through `REVIEW_REQUIRED`**, consistent with `CLINICAL_VALIDATION_FRAMEWORK.md`'s existing
"no single-reviewer / production requires double review" rule.

## 3. Waiver model (resolves the interaction-check gap from `CLINICAL_SAFETY_GATES.md` check 7)
A waiver is NOT a silent pass — it is a first-class, permanent record:
```
waiver: {
  gate: "CLINICAL_SAFETY_GATES.check_7_interactions",
  regimen_id, version,
  approved_by: <Sign-off Authority, named>,
  rationale: "<why this check cannot currently be satisfied and why publication proceeds anyway>",
  scope: "all regimens" | "this regimen only" | "<defined class>",
  recorded_at: timestamp,
  review_cadence: "<when this waiver itself must be reconsidered — e.g. next Interaction object type ships>"
}
```
A waived gate shows on the regimen's audit record (`KNOWLEDGE_AUDIT_MODEL.md`) permanently — a
physician viewing the recommendation five years later can see "interaction checking was waived on
this date, for this reason, by this authority," not a silent absence. **This design does not decide
whether check 7 should currently be waived at "all regimens" scope** — that is the governance
decision `CLINICAL_SAFETY_GATES.md` explicitly deferred to the Sign-off Authority; this section
defines the mechanism by which that decision, once made, is recorded and remains visible.

## 4. Certification is per-regimen-version, not a one-time system certification
Unlike P4.4's certification (which certified the Knowledge Base BUILD as a whole,
`PRODUCTION_SCORECARD.md`), regimen certification (this document) happens **per regimen version**,
continuously, as each one moves through the lifecycle. The system-level equivalent — "is the
Regimen Assembly Engine + Review Workflow + Safety Gates apparatus itself production-ready" — is a
separate, one-time (then periodically re-run) audit, structurally identical to the P4.4 Release
Readiness Review process (`PRODUCTION_SCORECARD.md`, `PROVENANCE_CERTIFICATION.md`) but scoped to
this new layer. This document does not re-run that audit (nothing has been built yet — P5.1/P5.2 are
design-only); it specifies that when P5.1/P5.2 move to implementation, the SAME Release Readiness
Review discipline this project has already proven (measured evidence, independent adversarial audit
before accepting a migration, code freeze during audit) applies again.

---

## Final answer — the governance model for a 10-year, physician-grade CDSS

**Every clinical fact enters through one deterministic pipeline, is assembled into one canonical
regimen model, and reaches a physician's screen only after passing three independently-necessary
gate categories (technical, medical, governance) — with every state transition, every review
verdict, every conflict resolution, and every waiver recorded append-only and permanently visible.**

Concretely, the governance model this P5.2 package specifies has five properties that make it
10-year-durable:

1. **No transition to `PHYSICIAN_APPROVED` or `PUBLISHED` is automatable** (`CLINICAL_KNOWLEDGE_LIFECYCLE.md`
   §3 hard rule) — a named, accountable human is always in that loop, permanently, by architecture
   not by policy discipline alone.
2. **Conflicts are never silently resolved** — both sides of a disagreement are stored, reviewed,
   and the decision (including why the loser lost) is permanent (`REVIEW_WORKFLOW_RFC.md` §2.6).
3. **Nothing is ever edited in place** — every correction, every re-review, every guideline update
   produces a new, linked version; history is never destroyed (`VERSIONING_GOVERNANCE.md`,
   `KNOWLEDGE_AUDIT_MODEL.md` §6).
4. **Gaps are recorded, not hidden** — where a check cannot currently be satisfied (interaction
   checking today), that is a visible, dated, accountable waiver, not a silent pass (§3). A system
   used for 10 years WILL have known limitations at any given time; what makes it trustworthy is
   that the limitations are documented, not that they don't exist.
5. **The same measured, adversarially-audited discipline that certified P4.4 applies again at every
   layer built on top of it** — this governance model is not a one-time design exercise but a
   process this project has already demonstrated it can execute (§4).

If forced to name the single design choice that most determines whether ANTIBIO is trustworthy in
year 10, it is this: **the system is architected so that trust does not depend on nothing ever going
wrong — it depends on nothing being able to go wrong silently.**
