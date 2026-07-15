# GOLDEN_DATASET_SPECIFICATION.md
## Production Golden Dataset for the Clinical Decision Engine · ANTIBIO · v1.0 · 2026-07-15

> Doctor-verified input→output pairs used to validate the (frozen) Clinical Decision Engine against
> Russian Ministry of Health clinical recommendations (клинические рекомендации). This document is
> the **normative specification**; it EXTENDS the already-existing infrastructure at
> `clinical_engine/golden_cases/` (do not fork a parallel format). Design/spec only — authoring the
> 500+ cases is a separate, physician-gated effort governed by `CLINICAL_VALIDATION_FRAMEWORK.md`.

## 0. Canonical location & reconciliation (IMPORTANT)
The golden set already lives at **`clinical_engine/golden_cases/`** and ships:
`schema.json` (Draft-07, the canonical case schema), `_TEMPLATE.json`, `runner.py` (the executor),
`README.md`, and 7 seed cases (positive + negative). **This spec adopts that schema as canonical.**
The earlier sibling docs (QA Program, Clinical Validation Framework) referenced a missing
`schema.json` — it exists; those references resolve here. All new golden cases MUST validate against
`clinical_engine/golden_cases/schema.json` (plus the additive fields in §3), be executable by
`runner.py`, and live under this folder.

## 1. Specification (purpose, scope, sourcing, sign-off)
- **Purpose.** Provide ≥500 physician-verified scenarios that lock the engine's clinical behaviour:
  same patient context + same KB version ⇒ same recommendation, and that recommendation matches the
  MoH guideline.
- **Scope.** Antibiotic therapy selection for the diagnoses covered by the current Knowledge Base
  (72 nosologies / 40 drugs at time of writing). Both **positive** cases (expected therapy) and
  **negative** cases (must-NOT-recommend / must-exclude) are first-class.
- **Sourcing of "expected" answers (source-of-truth hierarchy).** Expected fields are derived ONLY
  from: (1) the MoH clinical recommendation for that diagnosis (`clinrec_id` / `guideline_id`), then
  (2) the Knowledge Base object + its provenance, then (3) ID-specialist adjudication when the
  guideline is silent. Never from the engine's own output (no self-labelling), never invented.
  Every expected dose/frequency/duration cites the source guideline; illustrative values in THIS doc
  are marked `«ILLUSTRATIVE»` and are not authoritative.
- **Sign-off.** Each case's `provenance` block records the verifying physician + timestamp + source.
  A case is "golden" only after the double-review + adjudication process in
  `CLINICAL_VALIDATION_FRAMEWORK.md`. Provenance→guideline linkage is mandatory: `expect.guideline_id`
  must resolve to a real `clinrec_id` in `knowledge_base.json`.

## 2. Canonical schema (existing — `clinical_engine/golden_cases/schema.json`)
A case = `{ id, description, query, expect, provenance }`.
- `query.diagnosis`, `query.icd10`, `query.patient{age, weight_kg, pregnant, renal_function(СКФ
  ml/min), hepatic_impairment, allergies[](canonical classes), current_meds[]}`,
  `query.preferences{therapy_line, route_preference, population: adult|child|neonate}`.
- `expect` (only present fields are checked; ≥1 required): `first_drug_normalized`, `first_drug_ref`,
  `first_therapy_line`, `first_route (oral|iv|im)`, `min_accepted`, `max_accepted`, `accepted_empty`,
  `excluded_drug_refs[]`, `not_accepted_drug_refs[]`, `excluded_reason_contains`, `engine_note_code`,
  `guideline_id`, `not_guideline_id`, `trace_code`, `safety_flag_codes[]` (e.g. `ALLERGY`,
  `PREGNANCY_CI`), `first_candidate_confidence_range[min,max]`.

## 3. Additive expectation fields (proposed extension — additive, backward-compatible)
The user's required fields dose/frequency/duration/evidence are not yet in `expect`. Add them as
OPTIONAL keys (existing cases keep validating; `runner.py` checks only present fields):
```json
{
  "expect": {
    "first_dose":            "500 мг",
    "first_dose_mg_per_kg":  90,
    "first_frequency":       "каждые 8 ч",
    "first_duration":        "7 дней",
    "first_evidence_level":  "УДД 2 / УУР B",
    "expected_alternative_drug_normalized": "цефтриаксон"
  }
}
```
Tolerance: dose/frequency/duration compared with the tolerance rules in §5 (not naive string equality).
Adding these keys to `schema.json` is a P6 schema change (RFC-gated); until then they are documented
here and used by an extended runner.

## 4. Folder structure & naming
```
clinical_engine/golden_cases/
  schema.json                      # canonical (existing)
  runner.py  _TEMPLATE.json        # existing
  README.md
  <disease>/                       # NEW: per-disease subfolders as the set scales past ~30
    <disease>__<axis-tags>__<seq>.json
  # examples of scaled naming:
  cap/cap__adult_normal__001.json
  cap/cap__pregnancy_penicillin_allergy__014.json
  pyelonephritis/pyelo__peds_weightbased__003.json
  _negative/tonsillitis__not_pharyngitis__002.json
```
- `id` == filename stem, snake_case, unique. Positive cases named by diagnosis+axis; negative cases
  under `_negative/` with `not_`/`excluded_` intent in the name.
- Axis tags (compact): `adult|child|neonate`, `pregnancy`, `renal{mild|mod|severe}`,
  `allergy_{penicillin|cephalosporin|macrolide}`, `severe|mild`, `weightbased`.

## 5. Validation strategy
- **Executor.** `runner.py` loads each case, calls the engine, checks ONLY the present `expect`
  fields, emits pass/fail + the decision trace. CI gate G (see `PRODUCTION_QA_PROGRAM.md`): 100% of
  golden cases pass on the pinned KB version; any fail = blocking.
- **Match modes per field:**
  - Exact/normalized: `first_drug_normalized`, `first_route`, `first_therapy_line`, `guideline_id`,
    `trace_code`, `engine_note_code`, `safety_flag_codes`.
  - Set membership: `excluded_drug_refs` (⊆ excluded), `not_accepted_drug_refs` (∩ accepted = ∅).
  - Tolerance: `first_dose` (±0 for fixed-dose drugs; unit-normalized mg), `first_dose_mg_per_kg`
    (±5% rounding band), `first_frequency`/`first_duration` (canonicalized then equality; range
    guidelines accept any value inside the guideline's stated range), `first_candidate_confidence_range`
    (inclusive interval).
- **Determinism.** Each case runs twice; identical output required (guards against nondeterminism).
- **Disagreement triage.** A failing golden case → NOT auto-"fix the engine". First classify: (a)
  engine defect, (b) golden case wrong (re-adjudicate with physician), (c) KB/guideline changed
  (re-baseline with a DECISIONS entry). Route via the Root Cause Register; never silently edit the
  expected value to match engine output (that would defeat the oracle).

## 6. Coverage matrix (target ≥500 cases)
Stratification axes and target distribution. Cells are guidance, not a straitjacket; the binding
rule is **every supported diagnosis has ≥1 positive + ≥1 negative case, and every safety axis
(pediatric / pregnancy / renal / allergy) is represented for the diagnoses where it is clinically
relevant.**

| Axis | Buckets | Target share |
|------|---------|-------------|
| Disease | all KB nosologies (~72), weighted by clinical frequency | ≥1 pos + ≥1 neg each (~200 base) |
| Age | neonate / infant / child / adult / elderly | ≥15% pediatric, ≥10% elderly |
| Weight | low / normal / high (drives mg/kg) | pediatric cases weight-bearing |
| Renal (СКФ) | normal / mild(60-89) / moderate(30-59) / severe(<30) | ≥60 renal-adjusted cases |
| Pregnancy | yes / no | ≥40 pregnancy cases (CI-sensitive drugs) |
| Allergy | none / penicillin / cephalosporin / macrolide | ≥60 allergy-exclusion cases |
| Severity | mild / moderate / severe | severe drives iv + escalation |
| Polarity | positive / negative | ≥30% negative (exclusion proofs) |

**Hard-to-cover combinations (call out explicitly, prioritize for physician authoring):**
pregnancy + penicillin-allergy (few safe options); neonate + renal impairment; severe sepsis +
multiple allergies; pediatric weight-based dosing at renal-adjustment boundaries. These high-risk
intersections get mandatory adjudication and are tracked as a named coverage sub-goal.

**Coverage reporting.** A coverage report (analogous to `knowledge_coverage.py`) computes, per axis
bucket, `cases_present / cases_target`, and blocks certification if any safety-axis bucket is empty
for a diagnosis where it applies. `unmeasured = FAIL`.

## 7. Worked example scenarios (in the canonical schema; doses «ILLUSTRATIVE»)
> These follow the real `schema.json`. Doses/durations shown are ILLUSTRATIVE placeholders pending
> physician verification against the cited guideline; they are NOT authoritative clinical values.

```json
[
  {
    "id": "cap__adult_normal__001",
    "description": "CAP, взрослый 45 лет, без аллергий/беременности/почечной недостаточности — first-line пероральный аминопенициллин.",
    "query": {"diagnosis": "внебольничная пневмония", "icd10": "J18",
      "patient": {"age": 45, "weight_kg": 70, "pregnant": false, "renal_function": null, "hepatic_impairment": false, "allergies": [], "current_meds": []},
      "preferences": {"therapy_line": null, "route_preference": null, "population": "adult"}},
    "expect": {"first_therapy_line": "first_line", "first_route": "oral", "min_accepted": 1,
      "guideline_id": "g_cap_adult", "first_dose": "500 мг «ILLUSTRATIVE»", "first_frequency": "каждые 8 ч «ILLUSTRATIVE»", "trace_code": "DIAGNOSIS_RESOLVED"},
    "provenance": {"author": "<ФИО, инфекционист>", "verified_at": "<ISO8601>", "source": "КР ВП у взрослых"}
  },
  {
    "id": "cap__pregnancy_penicillin_allergy__014",
    "description": "CAP, беременность + аллергия на пенициллины — исключить бета-лактамы и тератогенные, предложить безопасную альтернативу (макролид, разрешённый при беременности).",
    "query": {"diagnosis": "внебольничная пневмония", "icd10": "J18",
      "patient": {"age": 29, "weight_kg": 68, "pregnant": true, "renal_function": null, "hepatic_impairment": false, "allergies": ["Пенициллины"], "current_meds": []},
      "preferences": {"population": "adult"}},
    "expect": {"safety_flag_codes": ["ALLERGY", "PREGNANCY_CI"], "not_accepted_drug_refs": ["amoxicillin", "doxycycline"], "min_accepted": 1},
    "provenance": {"author": "<ФИО>", "verified_at": "<ISO8601>", "source": "КР ВП + перечень при беременности"}
  },
  {
    "id": "pyelo__peds_weightbased__003",
    "description": "Острый пиелонефрит, ребёнок 6 лет 20 кг — доза по массе (мг/кг), пероральный цефалоспорин.",
    "query": {"diagnosis": "острый пиелонефрит",
      "patient": {"age": 6, "weight_kg": 20, "pregnant": false, "renal_function": null, "hepatic_impairment": false, "allergies": [], "current_meds": []},
      "preferences": {"population": "child"}},
    "expect": {"first_route": "oral", "first_dose_mg_per_kg": 8, "min_accepted": 1, "safety_flag_codes": []},
    "provenance": {"author": "<ФИО, педиатр>", "verified_at": "<ISO8601>", "source": "КР пиелонефрит у детей «ILLUSTRATIVE dose»"}
  },
  {
    "id": "cystitis__adult_renal_severe__007",
    "description": "Неосложнённый цистит, взрослый, СКФ 25 (тяжёлая ПН) — renal-adjusted доза; исключить нефротоксичные/накопительные.",
    "query": {"diagnosis": "острый цистит",
      "patient": {"age": 60, "weight_kg": 75, "pregnant": false, "renal_function": 25, "hepatic_impairment": false, "allergies": [], "current_meds": []},
      "preferences": {"population": "adult"}},
    "expect": {"safety_flag_codes": ["RENAL_ADJUST"], "min_accepted": 1, "excluded_reason_contains": "почеч"},
    "provenance": {"author": "<ФИО>", "verified_at": "<ISO8601>", "source": "КР цистит"}
  },
  {
    "id": "sepsis__severe_multiallergy__020",
    "description": "Сепсис, тяжёлое течение, аллергии на пенициллины и цефалоспорины — iv, эскалация, узкий выбор, требуется human review.",
    "query": {"diagnosis": "сепсис",
      "patient": {"age": 54, "weight_kg": 80, "pregnant": false, "renal_function": 55, "hepatic_impairment": false, "allergies": ["Пенициллины", "Цефалоспорины"], "current_meds": []},
      "preferences": {"population": "adult"}},
    "expect": {"first_route": "iv", "safety_flag_codes": ["ALLERGY"], "not_accepted_drug_refs": ["amoxicillin", "ceftriaxone"], "engine_note_code": "REVIEW_REQUIRED"},
    "provenance": {"author": "<ФИО>", "verified_at": "<ISO8601>", "source": "КР сепсис"}
  },
  {
    "id": "tonsillitis__not_pharyngitis__neg002",
    "description": "Негативный кейс: острый тонзиллит НЕ должен разрешаться в фарингит; доказательство отсутствия ложного guideline.",
    "query": {"diagnosis": "острый тонзиллит", "patient": {"age": 25, "weight_kg": 70, "pregnant": false, "renal_function": null, "hepatic_impairment": false, "allergies": [], "current_meds": []}, "preferences": {"population": "adult"}},
    "expect": {"not_guideline_id": "g_pharyngitis"},
    "provenance": {"author": "P1-B negative", "verified_at": "2026-07-11T00:00:00Z", "source": "diagnosis_index negative separation"}
  }
]
```
*(Cases 7–20 follow the same shape: neonate CAP; elderly renal-moderate; macrolide-allergy alt;
otitis pediatric weight-based; sinusitis first-line vs negative-not-chronic; UTI complicated iv;
pregnancy + normal renal; severe pneumonia escalation; duration-boundary case; evidence-level check
case; excluded-drug allergy proof; min/max accepted bound case; hepatic-impairment case; confidence-
range case. Each authored + physician-verified per the validation framework.)*

## 8. Certification tie-in
The Golden Dataset is the benchmark oracle for `CLINICAL_VALIDATION_FRAMEWORK.md` (MoH-guideline
benchmark gate, ≥98% overall / 100% critical) and a CI Quality Gate in `PRODUCTION_QA_PROGRAM.md`.
It does not gate P4.4 (Knowledge Base) closure; it gates the P6 Clinical Decision Engine. Building
the 500+ set is physician-capacity-bound and sequenced in `ANTIBIO_ROADMAP_P5_P10.md` (P6).
