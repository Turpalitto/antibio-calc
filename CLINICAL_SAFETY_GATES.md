# CLINICAL_SAFETY_GATES.md
## Mandatory Pre-Publication Safety Checks · P5.2 · Phase 3
## Status: PROPOSED (design only)

> Expands `REGIMEN_VALIDATION_GATES.md` Gate 3 (Clinical Safety) into the full nine-check list the
> mandate requires. These checks run at `ASSEMBLED → VALIDATED` (deterministic, machine-checkable)
> and are re-verified at `PHYSICIAN_APPROVED → PUBLISHED` (Phase 7 certification, final gate). All
> checks are fail-safe: they can only downgrade a regimen's readiness, never upgrade it.

## The nine mandatory checks

### 1. Medication safety
Drug is a recognized entity (resolvable `drug_normalized`, ideally `atc_code` present). An
unresolvable/unknown drug name → `REJECTED` (never published as free text masquerading as a
recommendation).

### 2. Dose completeness
`dose`+`dose_unit` present, OR `dose_mg_per_kg` present for weight-based regimens. A regimen with
neither → fails Gate 1 (`REGIMEN_VALIDATION_GATES.md`) already; this check additionally verifies the
dose is within a clinically plausible range (not zero, not absurdly high) — out-of-range → `REVIEW`,
never silently clamped or corrected.

### 3. Age restrictions
`adult`/`child` flags consistent with the dose data present (a `child=1` regimen with only an
adult-typical fixed dose and no `dose_mg_per_kg` → `REVIEW`, per `REGIMEN_VALIDATION_GATES.md` Gate
3's pediatric rule). Age boundaries (e.g. neonate vs. infant vs. child) are read from the guideline's
stated population, never inferred from dose magnitude alone.

### 4. Pregnancy
`pregnancy` field must be explicitly `true`/`false`/`null`(unknown) — never silently defaulted to
"safe." A `pregnancy=false` (contraindicated) regimen must carry a structured `Contraindication`
reference (`CLINICAL_REGIMEN_MODEL.md` §2.4); absence of that structured basis for a known-risk drug
class → `REVIEW`, not `PASS`.

### 5. Renal adjustment
`renal_adjustment` flag must be set when the drug class is known to require it (cross-checked
against the drug's ATC-code-linked renal-risk classification — a reference dependency, marked as
such: **this check's drug-class renal-risk list is an input this design assumes exists or must be
curated; not designed further here, per STRICT MODE**). A renal-risk drug with `renal_adjustment=0`
and no explicit "no adjustment needed" evidence → `REVIEW`.

### 6. Contraindications
Every structured `Contraindication` object linked to the regimen's diagnosis/drug/population (from
kb_p44, `CLINICAL_REGIMEN_MODEL.md` §2.4) must be represented in the regimen's output — a
contraindication known to kb_p44 but not surfaced on the assembled regimen is a **assembly defect**,
not a safety pass (Gate 2 provenance-completeness in `REGIMEN_VALIDATION_GATES.md` already covers
the traceability side; this check covers the completeness side — every known contraindication is
present, not just every present one is traceable).

### 7. Interaction checks
Drug-drug interaction data is **not currently modeled anywhere in the repository** (no `Interaction`
object type in kb_p44, no interaction table found in `normalized_regimens` or `metadata.sqlite` —
verified absent, not assumed). This check is therefore currently **UNSATISFIABLE** and must be
either: (a) explicitly waived with a documented governance decision (regimens publish without
interaction checking, flagged as a known limitation communicated to physicians), or (b) blocked on a
new extraction/reference dependency (an `Interaction` object type + a drug-interaction reference
source) before any regimen can pass this gate. **This design does not choose (a) or (b) — that is a
governance decision for the Sign-off Authority, recorded per `REGIMEN_APPROVAL_MODEL.md` §Waivers.**
Until decided, the honest state is: interaction checking is a documented gap, not a silently-passed
check.

### 8. Guideline freshness
`guideline_year` (from diagnosis_index, per `CLINICAL_REGIMEN_MODEL.md` §2.1) is checked against a
staleness threshold. A regimen sourced from a guideline whose publication/review cycle has lapsed
(per MoH's own review cadence — a reference fact not verified in this pass, **UNKNOWN**) does not
auto-fail, but is flagged for `REVIEW` with reason `STALE_GUIDELINE` — freshness is a review trigger,
not an automatic reject, because a stale-but-unchanged guideline may still be clinically current.

### 9. Provenance completeness
Every field's `field_sources` entry resolves to a real, provenance-complete kb_p44 object
(`REGIMEN_VALIDATION_GATES.md` Gate 2 / proposed `INV-18`). This is the check most directly inherited
from this project's certified P4.4 work — `original_text`, `guideline_id`, `layout_engine`,
`table_row`/`table_conf` where applicable, all non-null (the exact fields the P4.4 certification
proved 100% populated at full corpus scale, 2026-07-15).

## Check execution model
```
ASSEMBLED regimen
    │
    ▼
Checks 1,2,3,4,5,6,8,9 — deterministic, machine-evaluated
    │
    ├── any REJECT-level failure → REJECTED (never enters REVIEW_REQUIRED, terminal)
    ├── any REVIEW-level flag → REVIEW_REQUIRED (queued, REVIEW_WORKFLOW_RFC.md)
    └── all PASS → VALIDATED
    │
Check 7 (interactions) — currently UNSATISFIABLE; governance waiver required (see above)
    │
    ▼
VALIDATED regimen (eligible for REVIEW_REQUIRED trigger evaluation, CLINICAL_KNOWLEDGE_LIFECYCLE.md §3)
```

## Severity table

| Check | REJECT condition | REVIEW condition | Auto-PASS condition |
|---|---|---|---|
| 1. Medication safety | Unresolvable drug | — | Resolvable, ATC-coded |
| 2. Dose completeness | No dose data at all | Out-of-range value present | In-range, complete |
| 3. Age restrictions | — | Pediatric without weight-basis | Consistent age/dose |
| 4. Pregnancy | — | Contraindicated without structured basis | Explicit flag + basis (if contraindicated) |
| 5. Renal adjustment | — | Renal-risk drug, flag unset, no evidence | Consistent with drug-class risk |
| 6. Contraindications | — | Known contraindication not surfaced | All known contraindications present |
| 7. Interactions | N/A — gate unsatisfiable pending governance waiver | | |
| 8. Guideline freshness | — | Stale guideline | Within cadence |
| 9. Provenance completeness | Untraceable field | — | All fields traceable |

## Relationship to existing invariants
Checks 6 and 9 formalize into machine-checkable invariants already proposed in
`REGIMEN_VALIDATION_GATES.md` (`INV-18` provenance completeness) and this document proposes one more:
**`INV-22`** — every `ClinicalRegimen` linked to a kb_p44 Contraindication for its (diagnosis, drug,
population) key has that contraindication represented in its output fields. These join the existing
`knowledge_invariants.py` suite (INV-01..17, certified 2026-07-15) as the next extension, not a
parallel checker.
