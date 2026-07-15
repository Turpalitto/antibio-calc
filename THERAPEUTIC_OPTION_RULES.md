# THERAPEUTIC_OPTION_RULES.md
## Rules Separating ClinicalRegimen from TherapeuticOption · P5.5
## Status: ADOPTED

> Governs which of the two clinical-knowledge shapes a piece of guideline content belongs to.
> Grounded in `RC024_CLASS_LEVEL_ANALYSIS.md`'s finding that 57.6% of REJECTs are structurally a
> different kind of knowledge than a dosed regimen, not a defective one.

## The one dividing rule
**`ClinicalRegimen` = a specific drug + a specific dose. `TherapeuticOption` = a drug class or an
alternatives list, with no single dose.** If a piece of source content names a concrete agent with a
quantified dose, it is (or should become, once extraction is complete) a `ClinicalRegimen`. If it
names a class of agents, or lists several specific agents as interchangeable options without dosing
any of them, it is a `TherapeuticOption` — never force-fit into the regimen shape by inventing or
guessing a dose (this would violate `DOSE_NORMALIZATION_POLICY.md`'s absolute rule).

## ClinicalRegimen — unchanged eligibility (P5.1–P5.4, not modified)
Must have a specific `antibiotic`, a specific `dose` (or `dose_mg_per_kg`), and `route` — exactly
Gate 1's existing completeness requirement (`REGIMEN_VALIDATION_GATES.md`). Nothing about this
document changes that gate or the `ClinicalRegimen` model.

## TherapeuticOption — eligibility
A candidate is a `TherapeuticOption` if it matches `RC024_CLASS_LEVEL_ANALYSIS.md` category A
(therapeutic class recommendation) or B (alternative therapy statement) — i.e., no dose is present
AND no dose text is recoverable from the source (ruling out category C, which stays a `ClinicalRegimen`
candidate pending extraction fix), AND the source is not degenerate noise (ruling out category D).

## What TherapeuticOption is NOT allowed to do
- **Never carries a dose, route, frequency, or duration field.** If a specific dose is later found
  for one of its `alternatives`, that alternative becomes its own `ClinicalRegimen` candidate — it
  does not get bolted onto the `TherapeuticOption` as a "mostly a class, but here's one dose."
- **Never serves as an engine input directly.** The Clinical Decision Engine (frozen,
  `RecommendationCandidate` contract) consumes `ClinicalRegimen`-derived candidates only, per
  `CLINICAL_ENGINE_ADAPTER_RFC.md`. A `TherapeuticOption` is reference/explainability knowledge (e.g.
  "here are the classes considered for this indication, and why one might pick among them") — a
  future, explicitly governed extension would be needed before any engine consumption, out of P5.5
  scope.
- **Never silently absorbs a misclassified regimen.** If a candidate has ANY dose signal (even
  partial/unparsed, category C), it stays a `ClinicalRegimen` candidate, never becomes a
  `TherapeuticOption` "for convenience."

## Migration gate (Task 4 — REJECT → TherapeuticOption)
A REJECT `ClinicalRegimen` candidate becomes a `TherapeuticOption` **only if `has_complete_provenance()`
is true** (`source`, `source_page`, `source_quote`, `guideline_id` all present and non-empty) — per
the mandate's explicit "только если 100% provenance." A candidate matching category A/B but MISSING
any provenance field is NOT migrated — it remains an unmigrated REJECT, flagged, never silently
promoted to a governed knowledge type without full traceability.

## Lifecycle & governance
`TherapeuticOption` reuses the exact same `LifecycleState` machine as `ClinicalRegimen` (P5.2,
`CLINICAL_KNOWLEDGE_LIFECYCLE.md`) — the same human-review discipline applies: no automated
`PHYSICIAN_APPROVED`/`PUBLISHED`, append-only versioning, conflicts never silently resolved. The
governance layer does not need to be redesigned for the new type — only the clinical SHAPE changed.
