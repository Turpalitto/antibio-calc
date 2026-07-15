# KNOWLEDGE_PLATFORM_MIGRATION_RFC.md
## RFC — Migration Strategy, Rollback, Validation, Cutover · P5.0 · Phase 4
## Status: PROPOSED (documentation only, no implementation, no migration executed)

> Depends on: `SINGLE_SOURCE_OF_TRUTH_RFC.md` (the target model). This RFC is the HOW; that RFC is
> the WHAT. Also folds in the mandate's Phase 7 "Compatibility Layer", "Versioning", and "Rollback"
> RFC topics as sections below (see `EXECUTIVE_SUMMARY.md` for the file-consolidation rationale).

## Guiding constraint
No migration phase below may, at any point, require the Clinical Decision Engine to be down, to
change its frozen behavior, or to read from a source whose parity with today's `normalized_regimens.sqlite`
has not been proven on the full golden dataset. Every phase is additive until an explicit,
evidence-gated cutover step.

---

## Migration Phase 1 — Canonical schema extension (storage only, no data movement)
**Scope:** Add the `Regimen` object type to `kb_p44`'s schema (new `objects.type='Regimen'` rows +
a `regimen_facts` junction table referencing constituent atomic fact ids) and extend
`Provenance`/invariants to cover it (`INV-18`: every `Regimen` has ≥1 provenance record, either via
constituent facts or direct; `INV-19`: every `Regimen` maps 1:1 to the `RecommendationCandidate`
required-field set — see below).
**Exit gate:** schema migration designed as ONE atomic change (per this project's established
"fix the contract once" discipline — see `PROVENANCE_CERTIFICATION.md` precedent), reviewed against
`RecommendationCandidate`'s 24 fields for completeness. **No cutover risk** — nothing reads this yet.

## Migration Phase 2 — Dual ingestion (additive, both pipelines keep running unchanged)
**Scope:** Build a mapping layer: `metadata.sqlite::antibiotic_regimens` (validated=1 rows) →
canonical `Regimen` objects, using `medical_normalizer`'s normalization logic as a library call
(not via `normalized_regimens.sqlite` as an intermediate file — direct mapping, one fewer hop).
Run this ALONGSIDE the existing `build_normalized_sqlite.py` path (which continues to feed the
engine unchanged) — do not remove or modify it in this phase.
**Exit gate:** canonical `Regimen` count matches `antibiotic_regimens` validated count (2,675, or
current corpus figure at migration time); spot-field diff (dose/route/frequency/duration) between
old `normalized_regimens` rows and new `Regimen` objects for the same `regimen_id` is zero on a
sample, fully audited on 100% before Phase 4.

## Migration Phase 3 — Adapter build (new read path, engine untouched)
**Scope:** Implement a new reader satisfying the EXACT interface `SQLiteReader`/
`RegimenProviderAdapter` already expose to `Engine` (`clinical_engine/readers/sqlite_reader.py`),
but backed by the canonical store instead of `normalized_regimens.sqlite`. See
`CLINICAL_ENGINE_ADAPTER_RFC.md` for the port/adapter design in detail. The engine's `EngineConfig`
gains a feature-flag-style source selector (config-level, not a code branch inside `Engine`) — this
RFC does not specify implementation, only that the switch must be a configuration concern, not a
recompilation.
**Exit gate:** the new adapter passes the full `clinical_engine/golden_cases/` suite standalone
(engine wired to the new adapter in a test configuration only — production still on the old path).

## Migration Phase 4 — Shadow validation (dual-read, zero production impact)
**Scope:** Run both readers side-by-side against the SAME `PatientQuery` set (golden dataset +
a sampled replay of real query shapes, if such logs exist — **UNKNOWN, not verified in this pass
whether query logs exist**) and diff `RecommendationSet` outputs field-by-field. Log every
divergence with full context. Production traffic (if any exists at this stage — **UNKNOWN,
deployment status not verified**) continues to be served exclusively by the old path; the new path
is read-only shadow traffic, never returned to a caller.
**Exit gate:** zero unexplained divergence on the full golden dataset (500+ cases per
`GOLDEN_DATASET_SPECIFICATION.md`, once authored); any explained divergence (e.g. a genuine data
quality fix the new pipeline correctly makes) is documented and physician-reviewed per
`CLINICAL_VALIDATION_FRAMEWORK.md`, not silently accepted.

## Migration Phase 5 — Cutover + compatibility window
**Scope:** Flip the engine's configured source to the canonical-store adapter. Keep the old
`normalized_regimens.sqlite` path and `build_normalized_sqlite.py` tool intact but unused, for a
defined compatibility window (this RFC does not set a calendar duration — measured by "N consecutive
clean audit cycles," not by date, per this project's "measure, don't estimate" convention).
**Exit gate:** RC-019 closure criteria from `EXECUTIVE_SUMMARY.md` §Phase 9 all met; one full
Release-Readiness-Review-style audit cycle (mirroring the P4.4 process) executed against the
now-canonical, engine-serving store.

## Post-Phase-5: retirement (not a "Phase 6" — a separate, later decision)
Only after the compatibility window closes cleanly: retire `build_normalized_sqlite.py` and the
`normalized_regimens.sqlite` file generation (or repurpose it as a deliberate read-cache rebuilt
from canonical, if a query-layer caching need justifies it — see `QUERY_LAYER_RFC.md`). This RFC
does not authorize deleting `metadata.sqlite::antibiotic_regimens` — it becomes permanent ingestion
staging/audit trail, not disposable.

---

## Rollback plan (every phase)
| Phase | Rollback mechanism | Data at risk |
|---|---|---|
| 1 | Drop the new schema additions (additive-only columns/tables, no existing data touched) | None |
| 2 | Discard mapped `Regimen` objects; old pipeline is untouched and still authoritative | None (dual-write, old path primary) |
| 3 | Delete/disable the new adapter; engine config still points at old reader | None |
| 4 | Stop shadow traffic; no production behavior was ever routed through the new path | None |
| 5 | **Config-level revert** — flip `EngineConfig`'s source selector back to the old adapter. Because Phase 5 is a config change (per the Phase-3 constraint), rollback is a config change, not a data migration. Old path files are still intact (compatibility window). | None, provided the compatibility window (old files kept) has not yet closed |

**Rollback is only unavailable after the post-Phase-5 retirement step** — which is explicitly a
separate, later, evidence-gated decision, not part of cutover itself.

## Validation plan (summary; ties to `CLINICAL_VALIDATION_FRAMEWORK.md` and `PRODUCTION_QA_PROGRAM.md`)
- **Field-level parity** (Phase 2/4): every `RecommendationCandidate` field reproduced exactly or
  with an explained, physician-reviewed delta.
- **Golden-case parity** (Phase 3/4): 100% of `clinical_engine/golden_cases/` pass identically.
- **Determinism check**: same `PatientQuery` + same canonical snapshot version run twice ⇒ identical
  `RecommendationSet`, on both the old and new path, before AND after cutover.
- **Invariant coverage**: `INV-18`/`INV-19` (new) join the existing `knowledge_invariants.py` suite
  and must be 0-violation on the full canonical store before Phase 5.

## Cut-over strategy
Single config flip (Phase 5), preceded by Phases 1–4 which carry zero production risk by
construction (additive schema, additive ingestion, standalone adapter, shadow-only validation).
No "big bang" data migration ever occurs — the canonical store is built up incrementally and proven
before anything reads it in production.

## Compatibility strategy
Both pipelines run unmodified through Phase 4. The frozen `medical_normalizer` package is reused as
a library (not replaced) inside the new mapping layer — its clinical-text-normalization logic is an
asset, not legacy to discard. `clinical_engine/corpus/provenance.py` is kept as an independent
cross-check during the shadow phase (compare its resolved chain to the canonical store's native
provenance for the same `regimen_id` — a free second opinion on traceability correctness).
