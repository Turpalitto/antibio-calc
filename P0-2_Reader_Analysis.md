# P0-2 Reader Analysis (Current State - Read Only)

**Date:** 2026-07-10
**Task:** Document current readers for Regimen, Diagnosis, DrugSafety. No proposals, no code changes.

## Current Readers

### 1. Diagnosis Reader
**File:** clinical_engine/readers/diagnosis_reader.py

**Class:** JsonDiagnosisProvider (implements DiagnosisProvider Protocol)

**Responsibilities:**
- Load diagnosis_index (JSON) once at init.
- Provide lookup from diagnosis name or ICD-10 to list of DiagnosisEntry (guideline mappings).
- Support two JSON formats: bare list or {"meta": {...}, "entries": [...]}
- Build in-memory indexes for fast lookup (by lowercased name, uppercased ICD).

**Public Method:**
- lookup(diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]

**Inputs:** Optional diagnosis string, optional ICD-10 string.
**Outputs:** List of DiagnosisEntry (guideline_id, diagnosis_name, icd10_codes, guideline_title, guideline_year, revision_date, source_url). Empty list on no match (clinical "no data", not error).

**Current Usage:**
- DiagnosisMatch stage: resolve diagnosis -> guideline_ids.
- RegimenLoad stage: re-lookup to get guideline_year for join (see duplication below).

**Notes:** Caches entire index in memory. No write. Errors only on file not found or parse.

### 2. Drug Reference / Safety Reader
**File:** clinical_engine/readers/drug_reference_reader.py

**Class:** DrugReferenceReader

**Responsibilities:**
- Load drugs_reference from db/index.json once.
- Resolve normalized drug name to canonical drug_ref.
- Provide drug metadata for safety: interactions (free text), pregnancy_category (classified at load), renal_adjustment (free text).
- Build DrugInfo objects (forms, dilution limited fields, pediatric mostly None).

**Public Methods:**
- get_drug_info(drug_ref: str) -> DrugInfo | None
- resolve_drug_ref(drug_normalized: str) -> str | None
- get_interactions(drug_ref: str) -> str | None
- get_pregnancy_category(drug_ref: str) -> PregnancyCategory | None
- get_renal_adjustment(drug_ref: str) -> str | None

**Inputs:** drug_ref or drug_normalized string.
**Outputs:** DrugInfo or scalar safety data (many fields are free text per known gaps).

**Current Usage:**
- HardSafetyFilter: get_drug_info for allergy class, pregnancy, age, contraindications.
- RegimenLoad: resolve_drug_ref to fill drug_ref on candidate.
- InteractionCheck, Dose stages: indirect via candidate or safety flags.

**Notes:** Pregnancy classification is narrow keyword at load time. Most safety fields are prose (degraded mode expected). No parsing of interactions/renal at runtime.

### 3. SQLite / Regimen Reader
**File:** clinical_engine/readers/sqlite_reader.py

**Class:** SQLiteReader

**Responsibilities:**
- Wrap medical_normalizer.db.NormalizerDB (frozen, does not duplicate schema).
- Load regimens for specific guideline_ids, filtered by ValidationPolicy.
- Map RegimenRecord to RecommendationCandidate (many fields filled, drug_ref and guideline_year left None for later stages).

**Public Method:**
- load_regimens(guideline_ids: tuple[str, ...], policy: ValidationPolicy = STRICT) -> list[RecommendationCandidate]

**Inputs:** tuple of guideline_ids, ValidationPolicy (STRICT=PASS only, ALLOW_REVIEW=PASS+REVIEW, DEBUG/AUDIT=all).
**Outputs:** List of RecommendationCandidate (regimen_id, guideline_id, drug_normalized, dose/unit, route, frequency, durations, therapy_line, adult/child/pregnancy flags, atc, confidence, verdict, source_pdf/page/quote, diagnosis, mkb; drug_ref/guideline_year=None).

**Current Usage:**
- Exclusively in RegimenLoad stage.

**Notes:** Read-only. Errors on file not found, corrupt, or missing table. Filters at load time.

## Duplicated Logic

- **Re-lookup for guideline_year:** In RegimenLoad, after DiagnosisMatch has produced guideline_ids, it calls ctx.diagnosis_provider.lookup again (with patient diagnosis/icd10) to build year_by_guideline map. This is because PipelineState at that point carries only guideline_ids (not the full DiagnosisEntry objects from prior stage). Comment in code notes this is in-memory (no extra I/O due to cache).
- **Drug resolution split:** resolve_drug_ref called in RegimenLoad; full get_drug_info (for safety) in HardSafetyFilter. Safety data (pregnancy etc.) lives in reader but rules applied in stage + ClinicalConstants.
- **No single "safety" abstraction:** Drug safety concerns spread across DrugReferenceReader + HardSafetyFilter + ClinicalConstants.allergy_class_map.

## Implicit Interfaces (Current)

From StageContext (pipeline.py, under TYPE_CHECKING):
- ctx.diagnosis_provider : DiagnosisProvider (Protocol defined in diagnosis_reader)
- ctx.sqlite_reader : SQLiteReader
- ctx.drug_ref_reader : DrugReferenceReader

Stages expect these attributes on ctx. No formal Protocol for DrugSafety or Regimen yet (only Diagnosis has explicit Protocol).

## Summary of Responsibilities (Current State)

- **Diagnosis resolution:** diagnosis_reader (lookup by name/ICD -> guidelines + metadata)
- **Regimen loading:** sqlite_reader (by guideline_ids -> candidates, verdict filtered)
- **Drug reference/safety:** drug_reference_reader (resolve + metadata for safety checks)

All readers are read-only, init-load + cache, error via EngineError on resource issues.

This is the exact current state. No changes made.

---

## Minimal Provider Interfaces (Proposal for P0-2 - Wrap Only)

Goal: Stable abstract interfaces so Engine/Stages depend on Providers, not concrete readers. Adapters wrap existing readers. 100% identical behavior. Zero changes to logic or data.

### DiagnosisProvider (existing Protocol, promote/keep)
**Responsibilities:** Resolve patient diagnosis/ICD-10 to list of DiagnosisEntry (guideline mappings). Single source for diagnosis -> guideline resolution.

**Public Methods:**
- lookup(diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]

**Inputs:** Optional diagnosis name (case-insensitive match), optional ICD-10 (upper match).
**Outputs:** list[DiagnosisEntry] (deduped by guideline_id, preserving order of first appearance). Empty list = no match (clinical no-data).

**Invariants:**
- Case-insensitive for diagnosis name, upper for ICD.
- No duplicates by guideline_id.
- Empty list on no match (never EngineError for "not found").
- Deterministic.

**Error Model:** EngineError only on init/load (DIAGNOSIS_INDEX_NOT_FOUND, RESOURCE_PARSE_ERROR). Lookup failures are not errors.

### RegimenProvider (new minimal wrapper around SQLiteReader)
**Responsibilities:** Load filtered regimens/candidates for guideline_ids. Provide the raw normalized data for a set of guidelines.

**Public Methods:**
- load_regimens(guideline_ids: tuple[str, ...], policy: ValidationPolicy = STRICT) -> list[RecommendationCandidate]

**Inputs:** tuple of guideline_ids, ValidationPolicy.
**Outputs:** list[RecommendationCandidate] (drug_ref and guideline_year may be None; filled downstream).

**Invariants:**
- Only candidates matching the policy's allowed verdicts.
- No safety filtering or dose calc here (pure load + filter).
- Order not guaranteed (or per DB order).
- Deterministic given same DB snapshot + policy.

**Error Model:** EngineError on DB not found / corrupt (SQLITE_NOT_FOUND, SQLITE_CORRUPT). Empty list for guideline with no matching regimens (degrade, not error).

### DrugSafetyProvider (new minimal wrapper around DrugReferenceReader)
**Responsibilities:** Provide drug reference data and safety metadata. Resolve normalized names to refs. Single place for drug safety lookups.

**Public Methods:**
- get_drug_info(drug_ref: str) -> DrugInfo | None
- resolve_drug_ref(drug_normalized: str) -> str | None
- get_interactions(drug_ref: str) -> str | None
- get_pregnancy_category(drug_ref: str) -> PregnancyCategory | None
- get_renal_adjustment(drug_ref: str) -> str | None

**Inputs:** drug_ref (canonical) or drug_normalized (for resolve).
**Outputs:** DrugInfo (full metadata) or specific fields. PregnancyCategory enum; others str | None (free text for most).

**Invariants:**
- Pregnancy classification is fixed at load (narrow keywords).
- No runtime parsing of prose fields (per Invariant #13: interactions/renal/contraindications stay as text).
- Unknown drug -> None (degraded handling downstream).
- Synonym resolution is lower-case, deterministic.

**Error Model:** EngineError only on init (DRUG_REFERENCE_NOT_FOUND, RESOURCE_PARSE_ERROR). Lookups return None for unknown.

**Notes:** These are thin wrappers. No new logic. DrugSafetyProvider can internally use the reader + any needed constants if desired, but keep minimal.

---

## Migration Strategy (Incremental, Feature Flags, Zero Regressions)

**Principle:** Adapters first. Wrap, do not rewrite. Behavior identical. Rollback by flag.

**Steps:**

1. **Define the three Provider Protocols** (in models.py or clinical_engine/providers.py or extend readers).
   - Keep existing concrete classes as-is.
   - Create thin Adapter classes:
     - class DiagnosisProviderAdapter(DiagnosisProvider):
         def __init__(self, reader: JsonDiagnosisProvider): self._reader = reader
         def lookup(...): return self._reader.lookup(...)
     - Similarly for RegimenProviderAdapter (wraps SQLiteReader.load_regimens)
     - DrugSafetyProviderAdapter (wraps DrugReferenceReader methods)

2. **Add feature flag in EngineConfig:**
   - use_provider_ports: bool = False  # default off (legacy direct readers)
   - Or more granular: use_diagnosis_provider etc. Start with one flag.

3. **In Engine.__init__ (behind flag):**
   - Always create the concrete readers as today.
   - If flag: wrap them in Adapters and store as providers in context/state.
   - Pass providers to stages via StageContext (add fields: diagnosis_provider, regimen_provider, drug_safety_provider).
   - Keep legacy ctx.xxx_reader for transition if needed.

4. **Update Stages incrementally (one stage at a time, flag protected):**
   - Start with DiagnosisMatch (simple, only diagnosis_provider).
   - Then RegimenLoad (uses all three).
   - Then HardSafetyFilter, InteractionCheck, etc. (mainly drug safety).
   - Use if ctx.config.use_provider_ports: use provider else reader.
   - Or always go through ctx.provider if present.

5. **Update Engine creation / tests:**
   - Default remains legacy path.
   - Add tests that run with flag=True and assert identical RecommendationSet / traces / metrics (deep compare or structural equality).
   - Golden runner and perf tools can test both.

6. **De-risk / Rollback:**
   - Flag off = exact previous behavior.
   - Once all stages migrated and tests green (including cross-path equality tests), flip default to True.
   - Remove legacy reader paths in a later cleanup (after P0-4 or so).
   - Production Guard etc. unchanged.

7. **Testing Strategy:**
   - Existing tests continue to pass (legacy path).
   - New "provider path" tests assert bit-identical output.
   - Run full suite with flag both ways.
   - No behavior change = zero functional regressions.

**Files touched (minimal):**
- New: providers/ or additions to models.py for Protocols/Adapters.
- engine.py, pipeline.py (StageContext), relevant stages (flag guarded).
- Tests only for new paths + equality.

This isolates responsibilities behind stable interfaces while keeping 100% identical observable behavior. Pure wrap.

No changes to readers, no logic moves, no new features.

