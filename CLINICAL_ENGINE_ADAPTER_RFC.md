# CLINICAL_ENGINE_ADAPTER_RFC.md
## RFC — Clinical Decision Engine Consumes the Canonical Store · P5.0 · Phase 5
## Status: PROPOSED (documentation only, no implementation)

> Depends on: `SINGLE_SOURCE_OF_TRUTH_RFC.md` (target model), `KNOWLEDGE_PLATFORM_MIGRATION_RFC.md`
> Phase 3 (where this adapter is built). This RFC does not modify, reinterpret, or extend the frozen
> Clinical Decision Engine spec (`docs/superpowers/specs/clinical-decision-engine-v1.md`) — it
> specifies how the storage layer satisfies that spec's existing contract exactly.

## 1. The contract the adapter must satisfy (already frozen, already real — and already ported!)
**Correction after deeper repository read:** the engine does NOT depend on `SQLiteReader` directly.
It depends on a Port that already exists: `clinical_engine/readers/sqlite_reader.py` defines
`RegimenProvider(Protocol)` with exactly **one** method —
```python
class RegimenProvider(Protocol):
    def load_regimens(
        self, guideline_ids: tuple[str, ...], policy: ValidationPolicy = ValidationPolicy.STRICT
    ) -> list[RecommendationCandidate]: ...
```
— and a concrete adapter, `RegimenProviderAdapter(RegimenProvider)`, that is a thin, explicitly
documented pass-through: `"""P0-2: Thin adapter. Wraps existing SQLiteReader. 100% identical
delegation. No new logic."""` (`sqlite_reader.py:139`, verbatim comment). **The Ports & Adapters
pattern this RFC needs is not something to introduce — it already exists, one layer beneath what
`Engine` directly touches.** This materially simplifies the work: the new component is a second
`RegimenProvider` implementation, not a new abstraction.

Contract details (from `SQLiteReader`, the adapter's current sole implementation):
- Constructor takes a source path/handle and raises `EngineError(EngineErrorCode.SQLITE_NOT_FOUND
  | SQLITE_CORRUPT, ...)` on missing/invalid source (per the existing error taxonomy in
  `clinical_engine/models.py`).
- `load_regimens(guideline_ids, policy)` returns `RecommendationCandidate` objects (24-field
  dataclass, exact shape in `SINGLE_SOURCE_OF_TRUTH_RFC.md` §1) filtered by `ValidationPolicy`
  (`STRICT` → `PASS` only, `ALLOW_REVIEW` → `PASS`+`REVIEW`, `DEBUG`/`AUDIT` → unfiltered) — this
  policy enum and its semantics are frozen and must be reproduced exactly.
- `drug_ref` and `guideline_year` are populated LATER by other stages
  (`DrugReferenceReader`, `DiagnosisEntry`/diagnosis_index), not by this reader — the new provider
  must preserve this staging, not attempt to fill them early.
- Never writes. Read-only guarantee is load-bearing for the engine's determinism story.

## 2. Ports & Adapters design (using the EXISTING port, not a new one)
```
                    ┌─────────────────────────┐
                    │   Engine (frozen core)   │
                    │  clinical_engine/engine.py│
                    └────────────┬─────────────┘
                                 │ depends on (existing port)
                    ┌────────────▼─────────────┐
                    │  RegimenProvider (Port)   │  <- ALREADY EXISTS
                    │  load_regimens(           │     sqlite_reader.py:133
                    │    guideline_ids, policy)  │     Protocol, one method
                    │  -> list[RecommendationCandidate]
                    └────────────┬──────────────┘
                 ┌───────────────┴────────────────┐
                 │                                 │
   ┌─────────────▼─────────────┐    ┌──────────────▼──────────────────┐
   │ RegimenProviderAdapter      │    │ CanonicalStoreRegimenProvider    │
   │ (existing, unchanged)       │    │  (NEW — this RFC)                 │
   │ wraps SQLiteReader           │    │  implements RegimenProvider        │
   │ backed by                    │    │  directly against kb_p44's         │
   │ normalized_regimens.sqlite    │    │  Regimen objects (via              │
   │ via NormalizerDB (frozen)      │    │  KnowledgeRepository, see           │
   │                                │    │  QUERY_LAYER_RFC.md)                 │
   └────────────────────────────┘    └───────────────────────────────────┘
```
Both implementations satisfy `RegimenProvider` identically from `Engine`'s point of view; `Engine`'s
code does not change — only which concrete `RegimenProvider` its config wires up (Migration RFC
Phase 3/5). The existing `RegimenProviderAdapter` is left untouched; the new class is a sibling
implementation, not a replacement of or change to it.

## 3. `CanonicalStoreRegimenProvider` responsibilities
- **Single method to satisfy.** `load_regimens(guideline_ids: tuple[str, ...], policy:
  ValidationPolicy) -> list[RecommendationCandidate]` — filter the canonical store's `Regimen`
  objects by `guideline_ids` and map the `validation_verdict`-filtered results per `policy`, exactly
  reproducing `SQLiteReader.load_regimens`'s filtering semantics.
- **Query layer.** Delegates the actual lookup to `KnowledgeRepository` (see `QUERY_LAYER_RFC.md`),
  which exposes richer query methods (`by_guideline_id`, `by_drug_normalized`, etc.) internally —
  those are implementation detail behind this one engine-facing method, not separately exposed to
  `Engine`.
- **Shape mapping.** Map a canonical `Regimen` object (+ its constituent atomic facts, where
  present) into `RecommendationCandidate` exactly — every one of the 24 fields sourced from a named
  canonical field, with no field silently defaulted where the canonical data is genuinely present.
  Any field the canonical `Regimen` cannot supply is a blocking gap (see
  `KNOWLEDGE_PLATFORM_MIGRATION_RFC.md` Phase 1 exit gate), not a place to invent a placeholder.
- **Validation-policy filtering.** `validation_verdict` on `Regimen` must be populated by the
  ingestion mapping (Migration Phase 2) with the same vocabulary (`PASS`/`REVIEW`/etc.) the frozen
  spec expects — this is a data-mapping requirement, not new engine logic.
- **Determinism.** Reads are against a **pinned canonical snapshot version** (the store's
  `schema_version`/build identifier), never a live-mutating view — same query + same pinned version
  ⇒ same rows, always. This mirrors `kb_p44`'s existing append-only/versioned object model, which
  already provides this property; the adapter must not break it by, e.g., reading `status='active'`
  without also pinning a build/version identifier if the store is rebuilt concurrently.
- **Read-only.** No adapter method may write to the canonical store, matching `SQLiteReader`'s
  existing guarantee and the engine's safety model (frozen spec).

## 4. Caching, lazy loading, indexes, performance
Detailed in `QUERY_LAYER_RFC.md`. Summary constraint here: whatever caching strategy is chosen, it
must not change `Engine.recommend()`'s observable output — caching is a performance concern
strictly below the port boundary, invisible to the frozen core.

## 5. What does NOT change
- `Engine.recommend()`'s 10-stage pipeline (per `docs/superpowers/specs/clinical-decision-engine-v1.md`).
- `RecommendationCandidate`, `PatientQuery`, `RecommendationSet`, `ValidationPolicy`,
  `EngineErrorCode` — all frozen types, referenced not modified.
- `DrugReferenceReader`, `DiagnosisEntry`/diagnosis_index-based enrichment — untouched, still fill
  `drug_ref`/`guideline_year` after `RegimenLoad`, per existing staging.
- Safety gates, contraindication/pregnancy/renal/pediatric resolvers, explainability — all consume
  `RecommendationCandidate` post-load; they are unaware of which adapter produced it.

## 6. Failure modes specific to the adapter
| Failure | Required behavior |
|---|---|
| Canonical store unreadable/corrupt | `EngineError(SQLITE_CORRUPT, ..., stage="RegimenLoad")` — reuse the existing error code/stage, do not invent a new taxonomy. |
| Canonical `Regimen` missing a field `RecommendationCandidate` requires | Fail loudly at adapter load time (construction-time validation), never emit a candidate with a guessed/defaulted clinical field. Mirrors this project's "never infer downstream" rule from `PROVENANCE_SPECIFICATION.md`. |
| Snapshot version ambiguous (concurrent rebuild in progress) | Refuse to serve; the adapter must pin a version at construction and fail if it cannot resolve one — never silently read a half-built store (this is exactly the class of bug this session's PR-001/RC-017 work exists to prevent). |
