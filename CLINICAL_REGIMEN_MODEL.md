# CLINICAL_REGIMEN_MODEL.md
## Clinical Regimen Domain Model · ANTIBIO · P5.1
## Status: PROPOSED (design only — no code, no schema change, no DB migration)

> The formal domain model for a "clinical regimen" — the unit the Clinical Decision Engine consumes.
> This is the target that the Regimen Assembly Engine (`REGIMEN_ASSEMBLY_ENGINE_RFC.md`) produces
> from atomic `kb_p44` Knowledge Objects. Grounded in the two real models it must reconcile; every
> field is traced to its source or explicitly marked as a NEW dimension not present today.

## 1. The two real models this must reconcile (verified 2026-07-15, read-only)

### 1.1 `RecommendationCandidate` — the engine's INPUT contract (frozen)
`clinical_engine/models.py`, 24 fields: `regimen_id, guideline_id, drug_normalized, drug_ref,
dose, dose_unit, route, frequency, duration_min, duration_max, duration_recommended, therapy_line,
adult, child, pregnancy, renal_adjustment, atc_code, confidence, validation_verdict, source_pdf,
source_page, source_quote, source_section, diagnosis, mkb, guideline_year`. (`drug_ref`,
`guideline_year` filled downstream by `DrugReferenceReader`/diagnosis_index, not by the reader.)

### 1.2 `normalized_regimens` — the current serving store (41 columns)
`medical_normalizer/db.py`. Superset of the candidate on some axes (`drug_original`,
`drug_components`, `field_confidence`, review/approval fields, `normalizer_version`) — PRIMARY KEY
`(guideline_id, regimen_id)`.

### 1.3 What NEITHER model has today (gaps the target model must introduce)
| Requested dimension | In RecommendationCandidate? | In normalized_regimens? | In kb_p44? |
|---|:---:|:---:|:---:|
| pathogen | ✗ | ✗ | ✗ (no Pathogen object type) — **NEW dimension** |
| weight (as input driving mg/kg) | ✗ (only adult/child flags) | ✗ (`weight_based` flag exists in `antibiotic_regimens` staging, not carried) | partial (Dose objects may carry mg/kg text, unnormalized) |
| alternatives (linked) | ✗ (therapy_line only; alternatives are separate rows) | ✗ (separate rows by therapy_line) | ✗ (AgeRestriction/AlternativeTherapy entity types exist but are DROPPED by the KB builder — RC-009) |
| evidence level (УДД/УУР) | ✗ | ✗ | ✓ **Evidence objects exist (2,190)** — kb_p44 is the ONLY store with this |
| contraindications (structured) | ✗ (pregnancy/renal flags only) | ✗ | ✓ **Contraindication objects exist (841)** |

**Design consequence:** the target regimen model is a **superset** of both current models. Assembling
from `kb_p44` is not just "reshaping" — it can ADD evidence-level and structured contraindications
the current engine input lacks, which is a positive argument for the assembly approach (not merely a
migration cost). Conversely, `pathogen` and normalized `weight`/`mg-per-kg` are genuinely new and
must be sourced (pathogen: likely a NEW extraction dimension or diagnosis-linked reference table —
marked as a dependency, not designed here).

## 2. Clinical Regimen Domain Model (the target aggregate)

A `ClinicalRegimen` is an immutable, versioned aggregate. Fields grouped by concern; each notes its
source and whether it is required for the engine's frozen contract.

### 2.1 Identity & clinical context
- `regimen_id` (str, req) — stable id; assembly-derived, deterministic (see Assembly RFC §id).
- `guideline_id` (str, req) — the source КР (`clinrec_id`).
- `guideline_year` (int, opt) — from diagnosis_index, filled downstream (engine staging preserved).
- `diagnosis` (str, req) — normalized diagnosis name.
- `mkb` (str, req) — ICD-10 / МКБ-10 code.
- `pathogen` (str|null, **NEW, opt v1**) — target organism when the guideline specifies one
  (e.g. "Streptococcus pneumoniae"). Null when the guideline is empiric/syndrome-based. Sourcing is
  a NEW dependency (not in any current store) — v1 permits null, gated for future population.

### 2.2 Drug
- `drug_normalized` (str, req) — canonical drug name.
- `drug_original` (str, opt) — original wording (preserved per `PROVENANCE_SPECIFICATION.md`
  "never discard original wording"; sourced from kb_p44 Medication `original_text`).
- `drug_components` (list, opt) — for combinations (amoxicillin+clavulanate); already in
  normalized_regimens.
- `drug_ref` (str|null, opt) — resolved downstream by `DrugReferenceReader`, not by assembly.
- `atc_code` (str, opt) — ATC classification.

### 2.3 Dose / route / frequency / duration
- `dose` (float|null, req-ish) + `dose_unit` (str) — from kb_p44 Dose objects.
- `dose_mg_per_kg` (float|null, **NEW, opt**) — explicit weight-based dosing (pediatric); today only
  implicit. Populated when the source expresses mg/kg; enables the engine's Pediatric/Dose resolvers
  to compute from patient weight deterministically.
- `route` (str, req) — normalized (oral/iv/im/...).
- `frequency` (float|null, req-ish) — normalized administrations per day (or a canonical interval).
- `duration_min` / `duration_max` / `duration_recommended` (float|null) — the engine already models
  duration as a range; preserved exactly.

### 2.4 Population & safety modifiers
- `adult` (bool) / `child` (bool) — population applicability.
- `pregnancy` (bool|null) — safe/contraindicated/unknown in pregnancy.
- `renal_adjustment` (bool) — whether dose adjusts with renal function.
- `contraindications` (list[ref], **NEW-to-regimen, opt**) — references to kb_p44 Contraindication
  objects; structured, not just the pregnancy/renal booleans. This is net-new clinical value the
  assembly can surface.

### 2.5 Therapy positioning & alternatives
- `therapy_line` (str, req) — first_line / alternative / reserve / etc. (frozen vocabulary — must
  match what the engine expects).
- `alternatives` (list[regimen_id], **NEW-as-link, opt**) — explicit links to sibling regimens that
  are alternatives for the same diagnosis/population, instead of leaving alternatives as unlinked
  separate rows the engine must re-associate. Assembly can compute these deterministically from
  shared (diagnosis, population) + differing drug.

### 2.6 Evidence
- `evidence_level` (str|null, **NEW-to-regimen, opt**) — УДД/УУР grade, sourced from kb_p44 Evidence
  objects linked to the same guideline section. Net-new; the current engine input has no evidence
  grade at all.

### 2.7 Quality, validation, review (lifecycle)
- `confidence` (float) — overall assembly confidence (function of constituent-fact confidences —
  see Assembly RFC §confidence).
- `field_confidence` (dict) — per-field confidence (already in normalized_regimens).
- `validation_verdict` (str) — PASS / REVIEW / REJECT (frozen vocabulary the engine filters on).
- `review_status` / `reviewed_by` / `review_date` / `approved` / `manual_override` — human-review
  lifecycle, **preserved from normalized_regimens** (MR-5 in `RISK_REGISTER.md`: real approvals may
  already exist and MUST NOT be lost in migration).

### 2.8 Provenance (the full chain — detailed in `KNOWLEDGE_TO_REGIMEN_PIPELINE.md` §provenance)
- `provenance` (list) — for each constituent fact: pdf, page, table/cell (row/col/conf),
  original_text, the kb_p44 object id it came from, plus the regimen-level assembly record (which
  facts were combined, by which rule, at which snapshot version). A `ClinicalRegimen` with any field
  whose provenance cannot be traced to a source is invalid (a domain invariant — see Validation
  Gates RFC).

### 2.9 Versioning
- `version` (int) + `superseded_by` (regimen_id|null) — append-only, mirroring kb_p44's existing
  object versioning (superseded-on-conflict). A regimen is never mutated in place; a new guideline
  edition produces a new version linked to its predecessor.
- `snapshot_version` (str) — the canonical-store build identifier the assembly ran against
  (determinism anchor, per `QUERY_LAYER_RFC.md` §4).

## 3. Relationship to the frozen engine contract
Every field in `RecommendationCandidate` maps FROM a `ClinicalRegimen` field (the Assembly Engine's
job is exactly this mapping). The `ClinicalRegimen` carries MORE than the candidate needs
(pathogen, evidence_level, structured contraindications, linked alternatives, per-field provenance);
the mapping to the frozen candidate simply projects the subset the engine consumes today, leaving
the richer fields available for future frozen-spec amendments (governed, RFC-gated) and for the P5
Explainability/Search APIs.

## 4. What is deliberately NOT decided here
- Pathogen sourcing method (new extraction vs. diagnosis-linked reference) — a dependency, out of
  scope for the model definition.
- Whether `evidence_level`/`contraindications`/`alternatives` should be surfaced to the engine in v1
  or held for a governed spec amendment — a governance decision, not a modeling one.
- Physical storage layout (columns vs. junction tables) — that is `REGIMEN_ASSEMBLY_ENGINE_RFC.md`
  and the P5.0 `SINGLE_SOURCE_OF_TRUTH_RFC.md`'s concern, not the domain model's.
