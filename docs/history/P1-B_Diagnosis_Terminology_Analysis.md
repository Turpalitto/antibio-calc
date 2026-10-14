# P1-B Diagnosis Terminology — Analysis (Current State)

**Date:** 2026-07-11
**Phase:** P1-B Analysis. No code. Document only.
**Sources:** code, resources, tools, models, stages, extraction pipeline.
**Constraint:** No redesign. No P0/P1-A change. Focus diagnosis terminology sources, pipeline, ICD, synonyms, limits, physician impact.

## Current Diagnosis Terminology Sources

- diagnosis_index.json (resources/):
  - AUTO_GENERATED_DRAFT from metadata.sqlite antibiotic_regimens.
  - Fields per entry: guideline_id, diagnosis_name, icd10_codes (from mkb split), guideline_title, guideline_year, guideline_revision_date, source_url.
  - Meta: status AUTO_GENERATED_DRAFT, guideline_set_version, conflicts 101, duplicates 127, missing_icd10 2.
  - Curated version: diagnosis_index.curated.json (P0-4?).
  - Built by clinical_engine/tools/build_diagnosis_index_draft.py: SELECT DISTINCT clinrec_id, diagnosis, mkb, clinrec_name, publication_date. _split_icd10 handles JSON array or comma/semicolon. Dedup by (guideline, diagnosis, mkb). No synonym resolve.

- medical_normalizer/db.py, database.py (extraction):
  - Stores diagnosis (text), mkb_codes (comma), mkb_names.
  - No synonym norm for diagnosis_name. Direct from PDF extraction (Name, Mkbs).
  - In antibiotic_gate.py: mkb_codes extracted, _match_icd for abx relevance (prefix match on _ICD_ABX_EXACT).

- clinical_engine/resources/diagnosis_index.json: 895 entries, 294 guidelines. Used by JsonDiagnosisProvider.

## Current Normalization Pipeline for Diagnosis

- Extraction (src/pipeline):
  - PDF -> extractor -> database: diagnosis, mkb from "Name", "Mkbs" (MkbCode, MkbName).
  - No fuzzy/synonym for diagnosis name. Exact preserve.
  - mkb split to codes/names.

- medical_normalizer: focuses on drug (antibiotic, dose, etc.). Diagnosis/mkb stored as-is. No diagnosis synonym dict (unlike drug_synonyms).

- Build index: mechanical, preserve exact. _split_icd10: strip []"' , split ;, . No norm beyond that.

- In clinical_engine:
  - No further diagnosis norm. Direct to lookup.

## ICD Mapping Usage

- icd10_codes: tuple from split mkb (upper in index?).
- Lookup: icd10.strip().upper() exact match in _by_icd10.
- In PatientQuery: icd10 str | None.
- In DiagnosisEntry: icd10_codes tuple.
- In RecommendationCandidate: mkb str (from sqlite).
- In regimen_load: re-lookup by patient diagnosis/icd10 for year_by_guideline.
- In extraction: mkb_codes list.
- No cross-map (e.g. ICD to SNOMED), no prefix/fuzzy ICD.

## Synonym Handling

- None for diagnosis_name.
- Exact: diagnosis.strip().lower() in _by_name.
- Drugs have medical_dictionary synonyms/ATC, but diagnosis no.
- No diagnosis synonym dict or loader.

## Existing Limitations

- Exact match only: no fuzzy, edit distance, synonyms for diagnosis_name. "внебольничная пневмония" vs variant fails.
- Re-lookup in RegimenLoad (in-memory ok, but duplication).
- Curation: 101 conflicts (same diagnosis -> multiple guidelines, different ICD sometimes). AUTO_GENERATED_DRAFT.
- No traceability: no record of which name/ICD matched, why guideline chosen. Only NO_MATCH trace.
- ICD split basic, but no validation/norm (e.g. J18 vs J18.9).
- In index build: no dedup beyond exact key, no merge.
- Affects routing: wrong/no guideline_ids -> wrong/no regimens -> incomplete/unsafe recs.
- No integration with TerminologyProvider yet (P1-B).
- Production Guard on index status.

## Where Diagnosis Terminology Affects Physician-Visible Recommendations

- DiagnosisMatch: lookup -> guideline_ids. Wrong match -> irrelevant regimens in RegimenLoad.
- RegimenLoad: re-lookup year, then candidates. Bad ids -> bad candidates -> ranked recs.
- Traces: NO_MATCH -> engine_note "Diagnosis/ICD-10 not found".
- Safety: indirect, via wrong regimens (e.g. allergy mismatch if wrong guideline).
- Traceability: missing "how normalized, which synonym/ICD, why guideline".
- Physician: "Why this rec?" lacks diagnosis path. Black box for routing.
- Examples: CAP J18 -> g_cap_adult. If synonym miss, no recs (NO_REGIMENS_EXTRACTED).

## Summary of Diagnosis Terminology State

Sources: extraction (mkb/name exact) -> build (split, preserve) -> provider (exact lower/upper lookup).
Pipeline: no synonym/ICD norm for diagnosis (unlike drugs).
ICD: exact upper, basic split.
Synonyms: none.
Limits: exact-only, conflicts, no trace, re-lookup.
Impact: routing accuracy -> rec quality/safety. Needs synonyms, norm, trace for P1-B clinical value.

P1-B will address: diagnosis synonym handling, ICD norm?, provider for resolve/mapping with trace.

Analysis only. No changes.