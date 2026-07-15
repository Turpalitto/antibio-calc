# P0-3 Bundle Loader Analysis (Documentation Only)

**Date:** 2026-07-10  
**Phase:** Start of P0-3 per permanent workflow.  
**Status:** Analysis phase. No code, no changes.  
**Goal:** Document Bundle Loader as pure infrastructure. Define lifecycle, responsibilities, explicit MUST NOTs. Prepare for lightweight RFC.  
**Based on:** P0-1 (frozen BundleManifest + manifest.py + schema + examples), P0-2 (providers frozen), ARCHITECTURE_V3.md, ENGINEERING_MASTER_PLAN.md, DEVELOPMENT_BACKLOG.md (P0-3: Bundle-loader + hash/signature; DoD: tampered rejected; Production Guard reads status from manifest), current resource loading.

## Current State (Read-Only Snapshot)

- **BundleManifest**: Frozen (P0-1). Typed dataclass + validate_manifest + load_manifest in clinical_engine/manifest.py. Supports I10 (unknown optionals dropped). 4 example manifests in clinical_engine/resources/: regimen_bundle_manifest.json, safety_..., terminology_..., score_profile_.... Fields include: schema_version, version, requires_kernel, bundle_format, content_hash, bundle_id, bundle_type, curation_status, source_refs, signatures, depends_on, supersedes, expiry, freshness_policy, stats, notes. bundle_type examples: "regimen", "safety", "terminology", "score_profile".
- **No loader yet**: Manifests are present but unused for actual loading. No Bundle concept beyond manifest. No hash/signature verification in runtime paths.
- **Current resource loading** (scattered, direct, in engine/config/readers):
  - EngineConfig: hard-coded defaults to clinical_engine/resources/*.json and _REPO_ROOT/db/index.json (drug ref), sqlite_path (caller supplied).
  - Engine.__init__: direct SQLiteReader(config.sqlite_path), DrugReferenceReader(drug ref path), JsonDiagnosisProvider(diag index), _load_clinical_constants(...), _load_score_weights(...).
  - Readers: each __init__ does its own json.load / NormalizerDB.connect.
  - Production Guard (_guard_index_curation_status): inspects meta.status directly from loaded diagnosis json (not via manifest).
  - No content_hash verification anywhere. No requires_kernel compat check at load. No bundle root concept.
- **Bundle types today map to**:
  - regimen: (future) regimens data (sqlite via normalizer).
  - safety: clinical_constants.json + drug ref data.
  - terminology: medical_dictionary data + atc etc.
  - score_profile: score_profiles/default.json.
- **P0-3 scope (from backlog/plan)**: verified loader. Later P0-4 wraps resources into bundles so engine uses loader. P0-5 flag for legacy.
- **No medical knowledge in infra**: current loads are file I/O + parse only. Loader must preserve this.

## Bundle Loader Principles (Infrastructure Only)

- Pure infrastructure component. No domain knowledge.
- Generic: supports any future payload (SQLite, JSON, LanceDB, Parquet, ...). New types = new adapter/handler only. Core loader unchanged.
- Deterministic, offline, read-only (except open handles returned to caller).
- Reuses frozen manifest.py (no duplication, no change to BundleManifest).
- Side-effect limited to file reads + validation. No mutation.
- Feature-flag friendly for migration (coexist with direct loads during P0-4/P0-5).
- Returns loaded resource + manifest (for status, version, curation etc. to be used by guards/engine metadata).

## Documented Bundle Loader Lifecycle

Exact sequence for load_bundle(...):

1. **Resolve bundle location**  
   Input: path (dir containing manifest + payload(s), or direct manifest path, or bundle descriptor).  
   Find the manifest file (convention: *_bundle_manifest.json or manifest.json next to payload; or explicit).  
   Resolve payload location(s) by convention relative to manifest (e.g. sibling files or subdir named by bundle_id; no magic in core).

2. **Load + validate manifest**  
   Use existing load_manifest(path_or_dict) + validate_manifest.  
   Returns typed BundleManifest (I10 unknowns dropped).  
   Fail fast on schema errors.

3. **Compatibility checks** (pure version/format logic)  
   - requires_kernel: parse "X.Y" vs current ENGINE_VERSION ("1.0.0"). Reject if manifest requires higher minor/major than supported. (E.g. "1.1" vs "1.0" incompatible; "1.0" ok.)  
   - bundle_format: must be known/supported (via registered handlers; "v1" initial). Reject unknown format.  
   - bundle_type: accepted as-is (I10; no hard enum reject in loader).  
   - version / schema_version: basic format + (optional) semver compat notes.  
   - expiry / freshness_policy: if present and date past "now", emit warning or (configurable) reject.  
   - depends_on: record (resolution of deps is higher layer, not loader).  
   - curation_status: expose; do not interpret (Production Guard / caller decides).

4. **Integrity checks** (tamper detection)  
   - content_hash: compute hash of the primary payload content (algorithm from prefix e.g. sha256: of the data file(s) or canonical serialization of bundle contents). Compare exact match to manifest.content_hash. Reject on mismatch ("tampered").  
   - signatures: if present, stub verify (or skip for v0; future crypto adapter). Record presence.  
   - No trust of file mtime/size alone.

5. **Resource loading (dispatch only)**  
   - Determine format handler from bundle_format (or bundle_type + format for v0).  
   - Call registered adapter/handler(bundle_root, manifest, payload_paths) → loaded_resource.  
   - Handler returns opaque resource (dict for JSON, Path/handle for SQLite, bytes for future binary). Loader does not parse medical content.  
   - Support multiple resources per bundle if needed (e.g. constants + index).

6. **Return loaded artifact**  
   Return value: e.g. LoadedBundle(manifest: BundleManifest, resource: Any, bundle_path: Path, verified: bool, warnings: tuple).  
   Or minimal: the loaded resource + attached manifest for consumer (engine, guard).  
   Closeable if handles (context manager support).  
   Errors: specific BundleLoadError (wraps manifest errors, hash mismatch, compat fail, missing payload).

7. **Post-load (caller)**  
   - Production Guard reads curation_status from manifest (not raw meta).  
   - Engine metadata pulls version/guideline_version from manifest.  
   - Providers/readers initialized from loaded resource (P0-4).

All steps pure: no clinical rules, no reader instantiation inside loader.

## Every Responsibility (Explicit List)

- Locate/resolve bundle + manifest.
- Load raw manifest + delegate to frozen validate/load_manifest.
- Perform compatibility (kernel version, format, expiry).
- Perform integrity (hash verify of content, signature presence).
- Dispatch to format-specific resource loader (via registry only).
- Return loaded resource + manifest metadata.
- Error reporting with clear codes (e.g. MANIFEST_INVALID, HASH_MISMATCH, INCOMPATIBLE_KERNEL, PAYLOAD_MISSING).
- Support context (enter/exit for resource cleanup).
- Logging/trace of load steps (optional, non-clinical).
- Expose manifest fields for downstream (curation_status for guard, stats for telemetry, source_refs for provenance).

## What the Loader MUST NOT Do (Explicit, Non-Negotiable)

- MUST NOT contain any business / clinical / medical logic (no antibiotics, diagnoses, dosing, regimens, safety rules, interactions).
- MUST NOT know specifics of any bundle_type (no "if bundle_type == 'regimen' then load sqlite as regimens").
- MUST NOT implement or duplicate reader logic (JsonDiagnosisProvider, DrugReferenceReader, SQLiteReader, NormalizerDB stay outside).
- MUST NOT implement provider logic or call providers.
- MUST NOT perform decision logic, filtering, ranking, scoring, or any stage work.
- MUST NOT modify BundleManifest (frozen; no new required fields).
- MUST NOT change existing engine behavior or direct load paths (additive only; flag for P0-4/5).
- MUST NOT hardcode payload locations or formats in core (registry/adapters only; add new without touching loader).
- MUST NOT do network I/O, writes, or side effects beyond read + validation.
- MUST NOT interpret content_hash as anything but integrity (no content parsing).
- MUST NOT bypass validation for "convenience".
- MUST NOT embed knowledge of clinical_constants structure, diagnosis_index shape, etc. (handlers may, but core loader generic).
- MUST NOT alter provenance or add medical notes.
- MUST NOT depend on engine, stages, models beyond minimal (manifest types + errors).
- MUST NOT assume bundle is always on disk (future: support in-memory or archive, but start with path).

Violations of above = out of scope for P0-3.

## Design for Genericity (No Modification on New Types)

- Core: BundleLoader class (or functions).
- Registry (simple dict or @register decorator in separate module):
  ```python
  # in bundles/formats.py or similar
  FORMAT_HANDLERS: dict[str, Callable] = {}
  def register_bundle_format(fmt: str, handler: Callable[[Path, BundleManifest], Any]): ...
  ```
- Handlers added in P0-4 or later (e.g. V1JsonHandler, V1SqliteHandler, FutureLanceHandler).
- Loader: `def load(bundle_path: str | Path, *, strict: bool = True) -> LoadedResource: ...` dispatches `handler = FORMAT_HANDLERS.get(manifest.bundle_format)`.
- New format: register only; no edit to loader.py.
- bundle_format in manifest drives it (examples use "v1"; future "sqlite-v2", "parquet-1").
- Payload discovery: convention-based (manifest dir + bundle_id hints), passed to handler. Handler decides how to open (json vs sqlite connect).

## Compatibility + Integrity Details

- requires_kernel check: split on '.', compare major/minor. Current kernel "1.0.0" supports "1.0". Reject "2.0" or "1.1" if policy strict.
- bundle_format: allowlist via registered keys + "v1" default.
- content_hash verification: read payload bytes (or canonical), sha256 (or per prefix), compare. Support future algos.
- For composite bundles (multiple files): hash over manifest + sorted payload contents, or per-file + recorded.
- Expiry: use datetime; treat as soft (warn) or hard per config.
- Curation: loader surfaces; guard (in engine) consumes from manifest.

## Integration Notes (No Behavior Change Yet)

- P0-3 delivers loader only.
- Engine/config/readers unchanged.
- Later (P0-4): wrap current resources as "v0 bundles" (manifest + data side-by-side or in dir). Engine can load via loader then pass to readers/providers.
- Feature flag (P0-5): use_bundle_loader or per-resource. Legacy direct = identical output.
- Production Guard update (P0-3 or 4): read curation_status from loaded manifest instead of raw meta.
- Tests: must prove pure infra (no import of clinical models beyond manifest; no antibiotic strings in tests).
- Determinism: same bundle dir + same kernel → same loaded resource + manifest.
- Errors must not leak internals.

## Risks / Open (for RFC)

- How exactly associate manifest to payload for current flat resources? (dir convention, sidecar file, explicit in call).
- Hash scope for content_hash (single file vs bundle dir tar?).
- Return type: generic Any? Typed per format? Or Bundle wrapper always.
- Error types: new BundleError in models? Or reuse EngineError (but loader infra, may be pre-engine).
- Signature verification: stub or minimal (ed25519 deps? no for infra min).
- Multiple resources: return dict of resources keyed by type.
- Must stay minimal; no new deps.

## Next per Workflow

Analysis complete (this doc). Produce lightweight P0-3 Implementation RFC (public API for loader, lifecycle in contract, compat rules, registry strategy, DoD, acceptance, migration notes). No redesign. Reuse P0-1 artifacts. Then review → impl (generic only) → tests (infra only) → accept → freeze → full docs/audit/handoff.

**This document is the required pre-implementation documentation of lifecycle + responsibilities + MUST NOTs.**

No changes made to any source. Repository is truth.