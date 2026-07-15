# P1 Terminology Binding — Analysis (Current State, No Code)

**Date:** 2026-07-10  
**Status:** Analysis phase per workflow. P0 COMPLETE + FROZEN. P1 opened per ENGINEERING_MASTER_PLAN (no reordering without RFC).  
**Goal of this doc:** Document exact current state of terminology handling. Pure facts. No proposals, no redesign, no code.  
**Source:** Code reads, resources, medical_dictionary, models, stages, config.  
**Master Plan P1:** ATC/ICD-10 binding; allergy-class from ATC (fallback); ValueSet/ConceptMap. Acceptance: drug→ATC for ≥40; coverage-report; safety green.

## Current Terminology Landscape

### 1. Allergy Handling (Hard Safety)
- Source: clinical_engine/resources/clinical_constants.json
  - allergy_class_map: manual curation of ~17 classes (Пенициллины, Цефалоспорины, Макролиды, Фторхинолоны etc.).
  - Maps specific drug_ref (e.g. "amoxicillin" → "Пенициллины").
  - allergy_class_hierarchy: for broader matching.
  - Meta: DRAFT, pending doctor review. Same status as db/index.json. Not verbatim from "class" field.
- Usage: stages/hard_safety_filter.py
  - In allergy check (ABSOLUTE): ctx.constants.allergy_class_map.get(c.drug_ref)
  - Case-insensitive comparison (post M1 audit fix).
  - If drug_class unknown but patient has allergies → ALLERGY_UNVERIFIABLE WARNING (not silent include).
  - DrugInfo.drug_class comes from db/index.json "class" field.
- RecommendationCandidate has no direct allergy field; resolved via drug_ref in safety stage.
- Current limitation: manual map, not derived from ATC. ~34 original classes collapsed to 17.

### 2. ATC / Drug Classification
- medical_dictionary/drug_atc.json: schema "canonical_name_to_atc". Count: 0. Empty, "pending_manual_review".
- medical_dictionary/drug_groups.json: empty.
- medical_dictionary/drug_synonyms.json: 116 entries (canonical mapping).
- medical_normalizer/dictionary.py: loads drug_atc, drug_groups (currently empty).
- In engine data:
  - RecommendationCandidate.atc_code: populated from SQLite (atc_code column in normalized_regimens). Often present but not used for binding yet.
  - DrugInfo has no ATC field (only drug_class string).
- No ATC hierarchy or prefix matching implemented in clinical engine.
- medical_dictionary/metadata.json: drug_atc and drug_groups status "empty_pending_review". drug_synonyms loaded.

### 3. ICD-10 / Diagnosis Binding
- diagnosis_index.json (and .curated): contains icd10_codes per guideline mapping.
- models.DiagnosisEntry: icd10_codes: tuple[str, ...]
- models.PatientQuery: icd10: str | None
- models.RecommendationCandidate: mkb: str (from SQLite)
- Current use: DiagnosisMatch stage uses diagnosis_provider.lookup(diagnosis, icd10) to get guideline_ids.
- No normalization layer or ValueSet for ICD yet.
- tools/build_diagnosis_index_draft.py handles _split_icd10 (JSON array or comma).
- No ConceptMap or cross-terminology binding.

### 4. Other Terminology
- medical_dictionary has route, unit, frequency, duration, pregnancy, renal dictionaries (some reference-only).
- DrugReferenceReader (db/index.json): uses "class" for drug_class.
- No TerminologyProvider, no central binding service.
- Config/Profiles: no terminology paths.
- StageContext: passes ClinicalConstants (includes allergy map) but no terminology service.
- medical_normalizer: some parsers use dictionaries, but not wired to clinical decision for ATC/allergy.

### 5. Current Data Status (from metadata + resources)
- drug_synonyms: 116 (populated)
- drug_atc: 0
- drug_groups: 0
- allergy_class_map: ~17 curated classes (manual, draft)
- No automated ATC derivation.
- dictionary_candidates.json: 441 pending manual review (source for future ATC/synonyms).

### 6. Gaps vs P1 Target
- No ATC as primary key for drug identity.
- Allergy still on manual map (not ATC-derived with fallback).
- No ICD normalization or binding layer.
- No ValueSet/ConceptMap infrastructure.
- No coverage report for terminology resolution.
- drug_class is free string from source, not standardized ATC.

### 7. Dependencies for P1
- P0-2 Providers (already frozen): DrugSafetyProvider can be extended later.
- medical_dictionary (partially populated, review pending).
- db/index.json and clinical_constants (current sources of truth for class).

This is exact current state as of 2026-07-10. P1 Analysis complete. Next per workflow: lightweight RFC for P1 if needed, then implementation.

No changes made. Roadmap respected. P0 frozen. P1 Analysis documented.