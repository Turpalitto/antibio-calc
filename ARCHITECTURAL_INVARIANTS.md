# ANTIBIO — Architectural Invariants (Design by Contract)
## Permanent artifact · created 2026-07-14

> Invariants are not tests of behavior — they are **rules that must never be violated**, at any
> point, by any code path, on any input. Tests check examples; invariants check guarantees. Every
> invariant here is (a) stated in plain language, (b) machine-checkable against a Knowledge Base,
> and (c) enforced by `src/pipeline/knowledge_invariants.py`, which runs in CI (RC-007) and at
> milestone-closure. A violation is a release blocker, not a warning.
>
> Governed by `docs/governance/` (Clinical Governance + Repository Intelligence). Frozen scope
> unchanged. These invariants encode the Clinical Traceability Rule as executable contracts.

## Legend
- **ID** INV-NN · **Enforced**: ✅ checker implemented · 🔜 planned (needs schema/feature) ·
- Severity: all invariants are **blocking** unless marked *(advisory)*.

---

## Provenance & traceability

- **INV-01 — Every Knowledge Object MUST have ≥1 provenance record.** ✅
  No anonymous knowledge. `objects` without a `provenance` row = violation.
- **INV-02 — Every provenance MUST reference an existing source object.** ✅
  No `provenance.obj_id` orphaned from `objects`.
- **INV-03 — Every table-derived object MUST retain table provenance.** ✅
  If provenance `semantic_engine` indicates table origin (`semantic+table`) or `layout_engine != 'none'`,
  then `table_row`/`table_col` MUST be present. (Guards the exact RC-001 failure class.)
- **INV-04 — Every KB object MUST be reproducible from its source PDF.** 🔜
  Provenance MUST carry a resolvable `pdf` + `page`; a re-extraction of that page MUST be able to
  regenerate the object's content key. (Full check needs a reproducibility harness.)

## Clinical content contracts

- **INV-05 — Every Dose MUST have a unit.** ✅ *(advisory until RC-008 normalization pass)*
  A `Dose` object with a numeric value but no unit is unsafe. Currently advisory because table/
  free-text extraction still yields unitless doses (tracked under RC-008); becomes blocking after.
- **INV-06 — Every AlternativeTherapy MUST reference a Drug.** 🔜
  An alternative with no associated drug is meaningless. (Needs RC-009: AlternativeTherapy objects
  don't yet exist in the KB — this invariant is what will validate that fix.)
- **INV-07 — Every FirstLineTherapy MUST reference a Drug.** 🔜 (same dependency as INV-06.)
- **INV-08 — Every Recommendation MUST have ≥1 Version.** ✅
  `version >= 1` for all objects; no version-0 / null-version objects.
- **INV-09 — Every normalized drug MUST preserve original wording.** ✅ checker · **CURRENTLY
  FAILING (1442 violations) → RC-012.** A `Medication` whose provenance `normalized_value` is set
  MUST also retain `original_text` (Clinical Governance "never discard original wording"). The
  checker found a real defect (KB reads `item.get("text")` but builder stores wording under
  `"raw"`). This is the invariant system working as designed: the guarantee is stated, the checker
  enforces it, the violation is a blocking finding, not a silent gap.

## Lifecycle & versioning

- **INV-10 — Version history MUST be monotonic and append-only.** ✅
  A superseded object MUST have a successor with `version = prev+1`; no version reuse; history
  chain intact.
- **INV-11 — Every migration MUST preserve version history.** 🔜
  Any schema/data migration MUST NOT drop or renumber existing versions (checked by comparing
  version chains pre/post migration). Ties to RC-002.
- **INV-12 — Status MUST be one of the allowed lifecycle states.** ✅
  `draft | extracted | validated | reviewed | published | superseded | deprecated | archived |
  active`. Any other value = violation.

## Determinism & integrity

- **INV-13 — Content key MUST deterministically identify an object.** 🔜
  Same content ⇒ same `id`; guards against the `LIKE %substring%` dedup risk (RC-011).
- **INV-14 — No silent failure in value stages.** ✅ *(process invariant)*
  Extraction/layout/semantic MUST NOT contain bare `except: pass`; failures log + increment a
  metric. Checked by a source lint (grep-based) in CI. (Directly encodes the RC-001 lesson.)

---

## Enforcement
- Tool: `python -m src.pipeline.knowledge_invariants --db kb_p44.db` → reports each invariant
  PASS/FAIL with violation counts + sample offending IDs. Exit non-zero on any blocking violation.
- CI (RC-007) runs it on every change against a fixture KB.
- Milestone closure (governance Definition of Done) requires 0 blocking violations.
- New invariants are added here first, then implemented in the checker. An invariant is never
  weakened silently; downgrading blocking→advisory requires a DECISIONS.md entry with rationale.
