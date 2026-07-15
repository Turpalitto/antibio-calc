# P0-2 Implementation RFC (lightweight)

**Date:** 2026-07-10  
**Status:** Accepted + Implemented (wrap-only, equality test added). Ready for freeze.  
**Type:** Implementation contract only. No architecture.  
**Based on:** P0-2_Reader_Analysis.md (accepted mapping)  
**Principle:** Wrap only. Adapters only. 100% identical behavior. No redesign. No new logic. No optimizations. No behavior change.

## 1. Public Interfaces

Protocols define the contract. Existing readers satisfy via adapters or direct impl.

### DiagnosisProvider (existing, in clinical_engine/readers/diagnosis_reader.py)
```python
from typing import Protocol
from clinical_engine.models import DiagnosisEntry

class DiagnosisProvider(Protocol):
    def lookup(self, diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]: ...
```
- Input: optional diagnosis str (case-insens), optional icd10 str (upper).
- Output: list[DiagnosisEntry]. Empty list = clinical no-match (not error).
- Invariants: dedup by guideline_id, deterministic, cache-backed.

### RegimenProvider (new)
```python
from typing import Protocol
from clinical_engine.models import RecommendationCandidate, ValidationPolicy

class RegimenProvider(Protocol):
    def load_regimens(
        self, guideline_ids: tuple[str, ...], policy: ValidationPolicy = ValidationPolicy.STRICT
    ) -> list[RecommendationCandidate]: ...
```
- Input: tuple guideline_ids, ValidationPolicy.
- Output: list[RecommendationCandidate] (drug_ref/guideline_year often None; filled downstream).
- Invariants: policy-filtered verdicts only (STRICT=PASS etc.). Deterministic. Empty for no match.

### DrugSafetyProvider (new)
```python
from typing import Protocol
from clinical_engine.models import DrugInfo, PregnancyCategory

class DrugSafetyProvider(Protocol):
    def get_drug_info(self, drug_ref: str) -> DrugInfo | None: ...
    def resolve_drug_ref(self, drug_normalized: str) -> str | None: ...
    def get_interactions(self, drug_ref: str) -> str | None: ...
    def get_pregnancy_category(self, drug_ref: str) -> PregnancyCategory | None: ...
    def get_renal_adjustment(self, drug_ref: str) -> str | None: ...
```
- Inputs: drug_ref (canonical) or normalized (for resolve).
- Outputs: DrugInfo or scalars (free-text for interactions/renal per Invariant #13). None for unknown.
- Invariants: pregnancy classified at load (keywords). No runtime parsing. Deterministic synonym map.

All errors: only on init (EngineError for missing/corrupt resources). Lookups degrade to None/[].

## 2. Adapter Classes

Thin wrappers. Existing readers unchanged. 1:1 delegation.

```python
# Example locations: readers/diagnosis_reader.py, or dedicated adapters (minimal)
# Diagnosis: JsonDiagnosisProvider already implements the Protocol (no adapter strictly needed, but explicit ok)

class RegimenProviderAdapter(RegimenProvider):
    """Wraps SQLiteReader. Identical behavior."""
    def __init__(self, reader: "SQLiteReader") -> None:
        self._reader = reader

    def load_regimens(self, guideline_ids: tuple[str, ...], policy: ValidationPolicy = ValidationPolicy.STRICT) -> list[RecommendationCandidate]:
        return self._reader.load_regimens(guideline_ids, policy)

class DrugSafetyProviderAdapter(DrugSafetyProvider):
    """Wraps DrugReferenceReader. Identical behavior."""
    def __init__(self, reader: "DrugReferenceReader") -> None:
        self._reader = reader

    def get_drug_info(self, drug_ref: str) -> DrugInfo | None:
        return self._reader.get_drug_info(drug_ref)

    def resolve_drug_ref(self, drug_normalized: str) -> str | None:
        return self._reader.resolve_drug_ref(drug_normalized)

    def get_interactions(self, drug_ref: str) -> str | None:
        return self._reader.get_interactions(drug_ref)

    def get_pregnancy_category(self, drug_ref: str) -> PregnancyCategory | None:
        return self._reader.get_pregnancy_category(drug_ref)

    def get_renal_adjustment(self, drug_ref: str) -> str | None:
        return self._reader.get_renal_adjustment(drug_ref)
```

Adapters created in Engine. Readers stay in readers/.

## 3. Feature Flag Strategy

Legacy readers + provider ports coexist. Default = legacy (zero risk).

- Add to EngineConfig (clinical_engine/config.py):
  ```python
  use_provider_ports: bool = False  # default: legacy direct readers in ctx
  ```
- Engine always instantiates concrete readers (_sqlite_reader, _drug_ref_reader, _diagnosis_provider).
- If flag=True: create adapters wrapping them; pass providers to StageContext.
- Legacy ctx fields (sqlite_reader, drug_ref_reader, diagnosis_provider) remain during transition.
- Or: ctx always carries provider attrs; stages read via provider (legacy path keeps direct until migrated).
- Rollback: flag=False = exact prior path.
- Once equality proven, default can flip (later cleanup pass, separate).
- Granular if needed (per-provider flags), start single flag.

Coexistence: both paths exercised in tests. No shared mutable state.

## 4. Dependency Injection

Engine owns creation. Stages receive via immutable StageContext.

- Engine.__init__:
  - Always: self._sqlite_reader = SQLiteReader(...)
  - self._drug_ref_reader = ...
  - self._diagnosis_provider = JsonDiagnosisProvider(...)
  - If config.use_provider_ports:
    - self._regimen_provider = RegimenProviderAdapter(self._sqlite_reader)
    - self._drug_safety_provider = DrugSafetyProviderAdapter(self._drug_ref_reader)
    - # diagnosis_provider already or wrapped
  - Else: legacy readers.

- In recommend() / ctx creation:
  ```python
  ctx = StageContext(
      config=self.config,
      # legacy for compat during mig
      sqlite_reader=self._sqlite_reader,
      drug_ref_reader=self._drug_ref_reader,
      diagnosis_provider=self._diagnosis_provider,
      # new providers (always present or conditional)
      regimen_provider=getattr(self, '_regimen_provider', None) or adapter(...),
      drug_safety_provider=...,
      constants=...,
      score_weights=...,
  )
  ```
- Update StageContext (pipeline.py):
  Add:
  ```python
  regimen_provider: "RegimenProvider"
  drug_safety_provider: "DrugSafetyProvider"
  # keep legacy or alias during transition
  ```
- TYPE_CHECKING imports updated.
- Stages access ctx.regimen_provider.load... etc (or keep reader names temporarily behind flag).

Engine remains sole creator. No stage creates readers/providers.

## 5. Migration Sequence

Incremental. One module at a time. Flag-protected. Order by usage simplicity + coverage.

1. **Define contracts + adapters** (readers/*.py or models.py + new thin files if needed). No stage change. Tests for adapters alone (identity).
2. **Add flag** to EngineConfig + Profiles. Default False.
3. **Update Engine** (engine.py): creation + ctx wiring. Keep legacy ctx fields.
4. **Migrate stages (flag-guarded inside run or ctx):**
   - First: `stages/diagnosis_match.py` (only diagnosis_provider.lookup). Simplest.
   - Second: `stages/regimen_load.py` (all three: load + resolve + re-lookup for year).
   - Then safety/drug users:
     - `stages/hard_safety_filter.py`
     - `stages/dose_calculation.py`
     - `stages/dose_adjustment.py`
     - `stages/interaction_check.py`
   - Other stages (population, therapy, rank, trace, trace) untouched (no reader calls).
5. **Update tests** (incremental):
   - Existing tests default (flag=False) unchanged.
   - Add provider-path tests: Engine(config with use_provider_ports=True). Assert RecommendationSet == legacy path (accepted/excluded/safety_flags/traces/notes/metrics).
   - Full suite on both.
6. **Engine tests / stage tests / golden** cover both.
7. After all green + equality: RFC review/accept. Later: flip default, remove legacy reader attrs (post P0-2).

Exact order above. No parallel. Verify after each.

Modules first: diagnosis_match, regimen_load, hard_safety_filter (core path).

## 6. Definition of Done

- Protocols + adapter classes implemented (thin delegation).
- EngineConfig has use_provider_ports flag (default False).
- Engine creates/wires providers; StageContext exposes them.
- All reader-using stages migrated (flag guarded or via providers).
- Full pytest suite green on legacy path (default).
- Cross-path equality tests: identical outputs (deep on key structures).
- No code changes inside existing readers (JsonDiagnosisProvider, DrugReferenceReader, SQLiteReader).
- No behavior change: traces, exclusions, dosing, ranking, notes identical.
- Imports clean (TYPE_CHECKING where needed).
- No new public surface beyond the three providers.
- RFC_INDEX updated.

## 7. Acceptance Criteria

- `Engine(Profiles.production(sqlite=..., use_provider_ports=True)).recommend(q)` produces RecommendationSet bit-structurally equivalent (accepted, excluded, safety_flags, traces, engine_notes, runtime metrics structural) to flag=False.
- All existing tests (1159+) pass unchanged (legacy).
- New adapter/equality tests pass for provider path.
- 0 observable diff on real data (perf audit cases or fixtures).
- Stages no longer directly know concrete reader classes (depend on Protocol where accessed).
- Adapters pass through exactly (no added filters, sorts, transforms).
- Rollback via flag works: flag=False restores exact pre-P0-2 Engine.
- Docs: this RFC + handoff files updated post-impl.
- Zero impact on frozen items (BundleManifest, ARCHITECTURE_V3 invariants, models except plumbing).
- After acceptance: freeze providers contract (similar to P0-1).

**Post-approval:** proceed immediately to implementation per permanent workflow (no further arch review). Incremental + tests + acceptance + freeze + full handoff updates + consistency audit.

---

**End of RFC.** Only these 7 sections. Implementation contract only.