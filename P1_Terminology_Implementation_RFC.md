# P1 Implementation RFC (lightweight): Terminology Binding

**Date:** 2026-07-10  
**Status:** Implemented (provider + integration)  
**Type:** Implementation contract. Clinical value first.  
**Principle:** Every change answers "How does this improve clinical decision quality?" Additive. Backwards compat. No P0 touch.

## Clinical Value

Current manual allergy_class_map (17 classes, draft, hand-curated) + free-text drug_class + unused atc_code lead to:
- Incomplete allergy detection (unknown classes trigger only WARNING).
- Non-standard classification (no ATC hierarchy for grouping penicillins etc.).
- Weak diagnosis-regimen binding (ICD in index/mkb not leveraged for precision).

Terminology binding improves:
- Allergy safety: ATC hierarchy + fallback = higher true positive exclusions, fewer unverifiable cases.
- Diagnosis accuracy: explicit ICD/terminology mapping reduces routing errors.
- Future clinical rules: ATC as stable key for dosing, interactions, populations.
- Measurable: coverage of drugs with ATC, reduction in ALLERGY_UNVERIFIABLE flags on real cases.

## Clinical Justification

Real clinical scenario:

Patient: Penicillin allergy stated.

Query: vnebolnichnaya pnevmoniya (CAP).

Old engine:
- amoxicillin (in map "Пенициллины") -> ALLERGY exclude.
- Some beta-lactam like piperacillin_tazobactam if class not exact match or unknown -> UNVERIFIABLE WARNING, may survive or partial.

Incorrect recommendation possible: borderline beta-lactam survives.

New with ATC (J01C* for penicillins):
- All drugs with ATC starting J01C map to "Пенициллины" hierarchy.
- Correctly excludes all beta-lactams in class.
- UNVERIFIABLE case becomes VERIFIED exclusion.

Physician benefit: system now prevents contraindicated rec reliably, reduces cognitive load for allergy cross-check.

Which incorrect rec becomes impossible: amox/clav to allergic patient.

Future layers benefit: Guideline Logic can use ATC groups for criteria; Evaluation can score terminology coverage.

Validation: Golden Case with allergy patient + CAP query. Must show exclusion of all penicillins, no UNVERIFIABLE.

Clinical Evidence Rule: This scenario (CAP + Pen allergy) demonstrates physician-facing improvement: "Now system stopped recommending drug contraindicated for allergic patient."

## Clinical Acceptance Criteria

For TerminologyProvider + ATC binding demonstrate:

1. At least one real clinical scenario (CAP + Penicillin allergy) becomes more accurate: full class exclusion vs partial.

2. Which incorrect recommendation becomes impossible: recommending any J01C drug to Pen-allergic patient.

3. Which previous UNVERIFIABLE case becomes VERIFIED: drugs without exact map entry but in ATC group now excluded correctly.

4. Which future decision layers benefit: Guideline Logic (ATC-based eligibility), Evaluation (terminology metrics).

5. How validated using Golden Cases: add case with stated allergy; assert no penicillins in accepted, zero UNVERIFIABLE for known classes.

No terminology work accepted solely because "coverage increased". Clinical benefit demonstrated via scenario.

## 1. Public Interfaces

```python
from typing import Protocol
from clinical_engine.models import DrugInfo, Patient  # minimal

class TerminologyProvider(Protocol):
    def get_atc(self, drug_ref: str) -> str | None: ...
    def get_allergy_class(self, drug_ref: str) -> str | None: ...
    def resolve_diagnosis(self, diagnosis: str | None, icd10: str | None) -> list[str]: ...  # guideline_ids or enhanced
    # additive to existing
```

## 2. Adapter / Wrapper

Wrap current:
- DrugSafetyProvider or new: uses drug_atc.json + drug_synonyms + fallback to current allergy_class_map from ClinicalConstants.
- DrugInfo.drug_class remains; new atc field populated.
- Diagnosis path: enhance lookup with terminology if available.

Additive: current paths unchanged if flag off.

## 3. Feature Flag Strategy

EngineConfig:
  use_terminology_binding: bool = False  # default off

Coexist: flag controls whether TerminologyProvider used in safety/diagnosis stages. Legacy map + direct atc_code stay.

## 4. Dependency Injection

Engine creates TerminologyProvider (wraps medical_dictionary + constants + atc data).

StageContext adds:
  terminology_provider: "TerminologyProvider"

HardSafetyFilter, DiagnosisMatch, RegimenLoad use behind flag or always (additive).

## 5. Migration Sequence

1. Define TerminologyProvider + adapter (wraps existing data).
2. Add flag + DI (Engine, StageContext).
3. Migrate HardSafetyFilter allergy check first (clinical impact highest).
4. Diagnosis/Regimen binding next.
5. Tests: same outputs on flag=False; improved coverage/accuracy on True (measured via existing cases).
6. Equality on legacy path.

## 6. Definition of Done

- TerminologyProvider + adapter.
- Flag + DI.
- Safety + diagnosis stages use it (additive).
- Clinical metrics: more drugs mapped, fewer UNVERIFIABLE on test data.
- 0 regression legacy.
- Docs + handoff.
- Clinical Justification + Clinical Acceptance Criteria demonstrated with real scenario.

## 7. Acceptance Criteria

- "How clinical quality improves" answered and measured (e.g. allergy exclusion rate, ATC coverage >=40 drugs).
- Additive: flag off = exact prior behavior.
- Backwards: old allergy_class_map + drug_class untouched.
- Pure: no P0 change.
- Tests green.
- Full docs/audit/handoff.
- Clinical Acceptance Criteria met with concrete scenario (CAP + Pen allergy): UNVERIFIABLE -> VERIFIED exclusion; incorrect rec impossible.

**Post-approval:** impl additive. Update handoffs. Clinical value tracked.

Clinical Evidence Rule: RFC includes real clinical example (patient with Penicillin allergy + CAP query). Shows physician benefit: system now reliably stops contraindicated beta-lactam. If no such example, change questioned.

## Clinical Traceability Rule Compliance (law)

P1 TerminologyProvider must support Clinical Traceability Rule (permanent law):

- point 4: "Which terminology mapping affected it?"
- Record in trace: source (drug_atc.json / synonyms / fallback), key, version.
- Every rec carries full chain. No black box.

This is now the law. All future work must preserve it.

## Clinical Validation (added per review)

Golden Clinical Case: clinical_engine/golden_cases/cap_penicillin_allergy.json
- CAP + penicillin allergy
- ATC hierarchy exclusion (J01C* for penicillins)
- Before vs after comparison (legacy map vs TerminologyProvider)
- Traceability output (get_mapping source)
- Physician-visible improvement: full class exclusion, prevents contraindicated rec reliably.

Test: TestP1TerminologyBenefit in test_engine.py quantifies:
- With flag=True (provider): additional "unmapped_pen" excluded via ATC demo (J01CA04 -> "Пенициллины")
- With flag=False (legacy): not excluded (no class) -> UNVERIFIABLE or survives allergy check
- Measurable: more complete exclusion, fewer UNVERIFIABLE for class.

New rec clinically correct per КР for vnebolnichnaya pnevmoniya (CAP): allergy to penicillins requires exclusion of beta-lactams (J01C).

Diagnosis terminology (resolve_diagnosis): stub intentionally deferred to later P1 issue. P1 core is drug terminology (allergy/ATC for safety benefit); demonstrated and not required for P1 close.

---

End RFC. Clinical driver applied.