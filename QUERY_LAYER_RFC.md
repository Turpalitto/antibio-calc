# QUERY_LAYER_RFC.md
## RFC — Knowledge Repository, Ports, Caching, Indexing · P5.0 · Phase 5 (detail)
## Status: PROPOSED (documentation only, no implementation)

> Consolidates the mandate's "Knowledge Repository", "Repository Interfaces", and "Caching"
> sub-RFC topics (Phase 7) into one document, per the file-consolidation note in
> `EXECUTIVE_SUMMARY.md`. Depends on `CLINICAL_ENGINE_ADAPTER_RFC.md` for the consuming contract.

## 1. Current query mechanism (grounded)
Today, `kb_p44.db`'s only query path is `KnowledgeBase._get_by_key()`
(`src/pipeline/knowledge_base.py`), which matches `content LIKE '%<key-suffix>%'` — a substring
scan over serialized JSON, already logged as **RC-011** (medium severity, confirmed risk of
false-merge/false-miss, not yet quantified with data). This is adequate for the current write-path
use (dedup during ingestion, one lookup per incoming object, batch-oriented) but is **not** a query
layer suited to the engine's read pattern (`load_by_guideline`, `load_by_drug`, `load_by_verdict`,
potentially per-request in a served API per the P5 Knowledge Platform RFC). `Engine.__init__` opens
one `NormalizerDB` connection and reuses it (`sqlite_reader.py` docstring: "One connection is opened
at init and reused (spec §9.2 'SQLite connection reuse')") — i.e., today's engine query pattern is
already connection-reuse-aware; the new query layer must preserve at least this property.

## 2. Repository layer design
```
RegimenProvider (Port, Protocol)         <- ALREADY EXISTS: sqlite_reader.py:133
load_regimens(guideline_ids, policy)        one method, consumed by Engine
        │
        ▼  (implemented by CanonicalStoreRegimenProvider, CLINICAL_ENGINE_ADAPTER_RFC.md §3)
KnowledgeRepository (new)               <- the actual query implementation, NOT engine-facing
        │
        ├── by_guideline_id(id) -> list[Regimen]
        ├── by_drug_normalized(name) -> list[Regimen]
        ├── by_validation_verdict(v) -> list[Regimen]
        ├── all(limit=None) -> Iterator[Regimen]
        └── snapshot_version() -> str      <- pins the read to one build (determinism, §4)
        │
        ▼
kb_p44 storage (SQLite today; see §6 for the P7 scaling note)
```
`KnowledgeRepository` is the SSOT-side counterpart to `CanonicalStoreRegimenProvider` — the provider
maps `Regimen → RecommendationCandidate` and satisfies the engine's one-method port; the repository
maps `query → Regimen` and is never seen by `Engine` directly. Splitting these two concerns means
the repository has no knowledge of the engine's frozen types, and the provider has no knowledge of
SQL/indexing — each can be reasoned about and tested independently. `KnowledgeRepository`'s richer
query surface (`by_drug_normalized`, `by_validation_verdict`, etc.) exists for uses beyond the
engine's single `load_regimens` call — e.g. the P5 Knowledge Query/Search APIs
(`docs/rfc/P5_KNOWLEDGE_PLATFORM_RFC.md`) can consume the same repository.

## 3. Indexing strategy (replaces RC-011's substring scan for the read path)
Real content-addressable lookups instead of `LIKE '%...%'`:
- `guideline_id`, `drug_normalized`, `validation_verdict` as **actual indexed columns** on the
  `Regimen` table (not scanned out of a JSON blob), mirroring the existing precedent already in the
  repo: `src/pipeline/database.py`'s `antibiotic_regimens` table already has
  `idx_regimens_diagnosis`, `idx_regimens_mkb`, `idx_regimens_antibiotic`,
  `idx_regimens_antibiotic_norm`, `idx_regimens_age`, `idx_regimens_code_version`,
  `idx_regimens_validated` — i.e. **this indexing pattern already exists in the codebase** for the
  LLM pipeline's staging table; the canonical store's `Regimen` table should adopt the same
  discipline rather than inventing a new one.
- The atomic-fact side (`objects`/`provenance` tables) keeps its existing `_content_key`-based dedup
  for the *write* path (ingestion); RC-011 is resolved by adding a real indexed key column there too
  (out of scope for this RFC to redesign — tracked as RC-011's own resolution, referenced not
  duplicated here).

## 4. Determinism: snapshot versioning
Every `KnowledgeRepository` instance pins a `snapshot_version()` at construction (the store's
`schema_version` plus a build/checkpoint identifier — `kb_p44`'s rebuild process already produces a
checkpoint file, `kb_p44.checkpoint.json`, that can serve as this identifier's source). All reads
within that instance's lifetime are against that pinned version. A concurrent rebuild (as this
project ran repeatedly this session) must not be visible mid-read — this directly generalizes the
lesson of RC-017 (partial/inconsistent reads causing silent data loss) to the query layer.

## 5. Caching strategy
- **What is cached:** `Regimen`-to-`RecommendationCandidate` mapped results, keyed by
  `(guideline_id | drug_normalized | verdict query, snapshot_version)`. Cache keys MUST include the
  snapshot version so a store rebuild invalidates stale entries automatically rather than requiring
  manual cache-busting.
- **What is never cached:** the pinning decision itself (always re-resolved at repository
  construction) and anything read under `ValidationPolicy.DEBUG`/`AUDIT` (these are diagnostic reads
  that should always see current state, not a cached view).
- **Cache tier:** in-process (per the engine's existing single-connection-reuse pattern) is
  sufficient for the current single-process deployment model (no evidence in the repo of a
  distributed/multi-process deployment — **UNKNOWN**, not verified). A distributed cache (Redis or
  similar) is P7 (Production Ecosystem) scope if/when the engine is deployed as a multi-instance
  service — not a P5 concern.

## 6. Lazy loading & performance
- `all(limit=None)` must remain lazy (an iterator, as `NormalizerDB.load_all(limit)` already is by
  signature) — never force-materialize the full canonical store into memory for a single query.
- No numeric performance baseline exists in the repository today for `Engine.recommend()` latency —
  this is **UNKNOWN** and must be measured (not assumed) before/after the adapter swap, per
  `KNOWLEDGE_PLATFORM_MIGRATION_RFC.md` Phase 4/5 exit gates.

## 7. Read-only guarantees
Both `KnowledgeRepository` and `CanonicalStoreAdapter` are read-only by construction — no method on
either exposes a write/insert/update path. Ingestion (Migration Phase 2) writes through
`KnowledgeBase.add_document()` exclusively, the same single write path `kb_p44` already enforces.
This preserves the existing separation the P4.4 certification already relies on (`KnowledgeBase` is
the only writer; every reader — including the future engine adapter — is downstream and read-only).

## 8. Scaling note (P7 boundary, explicitly out of scope here)
`ENTERPRISE_ARCHITECTURE_REVIEW.md` EAR-5 already flagged that file-based SQLite with hardcoded
local paths will not survive P7's service-deployment model. This RFC's repository/port design is
deliberately storage-agnostic at the interface level (`KnowledgeRepository` is a Python interface,
not a SQL-coupled one) specifically so that a P7 migration to a networked datastore does not require
touching `CanonicalStoreAdapter` or the engine again — only `KnowledgeRepository`'s implementation.
This is noted, not designed, here — full design is P7 scope.
