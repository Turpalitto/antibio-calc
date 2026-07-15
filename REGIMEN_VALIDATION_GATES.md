# REGIMEN_VALIDATION_GATES.md
## Validation Gates — Assembled Regimen → Clinical Engine · P5.1
## Status: PROPOSED (design only)

> The gates every `ClinicalRegimen` must pass before the Clinical Decision Engine may serve it.
> Gates are ordered and fail-closed: a regimen that fails any gate does not reach the engine as an
> approved candidate. Ties into `CLINICAL_VALIDATION_FRAMEWORK.md` (the clinical process) and the
> engine's existing `ValidationPolicy` (STRICT/ALLOW_REVIEW/DEBUG/AUDIT).

## Gate ordering (fail-closed, in sequence)
```
Assembled ClinicalRegimen
  │
  ├─ Gate 1: Required Fields  ──fail──▶ REJECT (incomplete, quarantined)
  ├─ Gate 2: Structural/Provenance ─fail─▶ REJECT (untraceable)
  ├─ Gate 3: Clinical Safety  ──fail──▶ REJECT (unsafe) / REVIEW (uncertain)
  ├─ Gate 4: Conflict State   ──conflict─▶ REVIEW (both siblings surfaced)
  ├─ Gate 5: Human Review     ──pending─▶ held (not served)
  ├─ Gate 6: Approval         ──not approved─▶ served only under ALLOW_REVIEW/DEBUG, never STRICT
  ▼
Approved regimen (validation_verdict=PASS, approved=1) → engine (STRICT-eligible)
```

## Gate 1 — Required fields
Every regimen must have, non-null: `guideline_id`, `diagnosis`, `mkb`, `drug_normalized`, `route`,
`therapy_line`, and at least one of `dose`/`dose_mg_per_kg`. Missing any → `REJECT` with the missing
field named in `assembly_trace` (never defaulted — the RC-012/RC-001 "no silent completion" rule).
This mirrors kb_p44's existing `_validate_basic` (Medication needs name; Dose needs value) extended
to the regimen aggregate.

## Gate 2 — Structural / provenance integrity
- Every field has a `field_sources` entry pointing to a real kb_p44 object id (no orphan fields).
- Every constituent object's provenance resolves to a real pdf/page (reuse `knowledge_invariants.py`
  INV-01/02 semantics at the regimen level → propose INV-18: every ClinicalRegimen field traces to
  a provenance-complete source object).
- `snapshot_version` and `assembly_ruleset_version` present (reproducibility anchors).
Fail → `REJECT` (untraceable regimen — inadmissible in a certified CDSS).

## Gate 3 — Clinical safety checks (fail-safe)
Deterministic safety rules that do not require human judgment:
- Dose within a plausible clinical range for the drug (max-dose ceiling) — over-ceiling → `REVIEW`
  (never auto-`PASS`).
- Pediatric regimen (child=1) must have `dose_mg_per_kg` OR an explicit pediatric dose — else
  `REVIEW` (pediatric dosing must be weight-explicit; ties to Coverage.pediatric=0% gap, RC-009).
- Pregnancy-contraindicated drug marked `pregnancy=false` must carry the contraindication reference
  (structured, from kb_p44 Contraindication objects) — missing structured basis → `REVIEW`.
- Route/drug compatibility (e.g. a drug with no oral form marked route=oral) → `REVIEW`.
These are checks, not overrides: they can only downgrade to REVIEW/REJECT, never upgrade to PASS.
The engine's own safety gates (frozen) still run downstream — this gate is an ADDITIONAL upstream
safety net at assembly time, not a replacement.

## Gate 4 — Conflict state
If assembly recorded an unresolved conflict (Assembly RFC §5 rule 5), the regimen and its sibling
are both flagged `REVIEW` with the `conflicts` record attached. Neither is auto-approved. A physician
adjudicates per `CLINICAL_VALIDATION_FRAMEWORK.md` (double-review + adjudication).

## Gate 5 — Human review
- `review_status` lifecycle: `pending → in_review → reviewed` (+ `reviewed_by`, `review_date`).
- Preserved from `normalized_regimens` — **existing approvals must migrate intact** (MR-5). A
  regimen whose constituent data is unchanged from an already-approved `normalized_regimens` row
  should carry that approval forward, not require re-review (migration must prove data-equivalence to
  do this — see `MIGRATION_PLAN_NORMALIZED_REGIMENS.md`).
- Regimens touching high-risk intersections (pregnancy+allergy, neonate+renal — the hard-to-cover
  cells from `GOLDEN_DATASET_SPECIFICATION.md`) require mandatory review regardless of confidence.

## Gate 6 — Approval
- `approved=1` is the terminal gate. Only approved regimens are eligible under
  `ValidationPolicy.STRICT` (the engine's production policy). `REVIEW`-state regimens are visible
  only under `ALLOW_REVIEW`/`DEBUG`/`AUDIT` (existing frozen policy semantics — reused exactly).
- Approval authority and record contents per `CLINICAL_VALIDATION_FRAMEWORK.md` §Approval workflow.

## Mapping to the engine's ValidationPolicy (frozen — reused, not changed)
| Gate outcome | validation_verdict | STRICT | ALLOW_REVIEW | DEBUG/AUDIT |
|---|---|:---:|:---:|:---:|
| all gates pass + approved | PASS | served | served | served |
| conflict / safety-uncertain / review-pending | REVIEW | hidden | served | served |
| required-field / provenance / safety fail | REJECT | hidden | hidden | served (audit only) |

This table is exactly the existing `_VERDICTS_BY_POLICY` semantics in
`clinical_engine/readers/sqlite_reader.py` — the assembly/validation layer produces verdicts the
frozen engine already knows how to filter. No engine change.

## Invariants added (join `knowledge_invariants.py` suite)
- **INV-18** — every ClinicalRegimen field traces to a provenance-complete source object.
- **INV-19** — every ClinicalRegimen maps 1:1 onto the RecommendationCandidate required-field set
  (no engine-required field unsatisfiable).
- **INV-20** — no regimen with `validation_verdict=PASS` has an unresolved conflict or a
  REJECT-level safety failure (consistency of the verdict with the gate outcomes).
- **INV-21** — every `approved=1` regimen has a non-empty `reviewed_by` and `review_date`
  (no approval without an accountable human).
