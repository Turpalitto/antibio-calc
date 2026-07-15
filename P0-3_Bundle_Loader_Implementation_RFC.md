# P0-3 Implementation RFC (lightweight): Bundle Loader

**Date:** 2026-07-10  
**Status:** Accepted + Implemented + Frozen (pure infra contract locked)  
**Type:** Implementation contract only. Pure infrastructure.  
**Based on:** P0-3_Bundle_Loader_Analysis.md (lifecycle/responsibilities/MUST NOTs documented). P0-1 frozen BundleManifest + manifest.py. P0-2 providers frozen. ENGINEERING_MASTER_PLAN + BACKLOG (P0-3: verified loader + hash/signature; DoD tampered rejected + guard uses manifest status).  
**Principle:** Generic infra only. Reuse frozen artifacts. New bundle types = new adapters only. No behavior change. No medical logic. BundleManifest unchanged.

## 1. Public Interfaces

Core loader API (new module e.g. clinical_engine/bundles/loader.py or clinical_engine/loader.py for minimality; export from clinical_engine).

```python
from pathlib import Path
from typing import Any, Callable, Protocol
from clinical_engine.manifest import BundleManifest

class BundleLoadError(Exception):
    """Infrastructure error for bundle load failures (hash, compat, manifest, missing payload)."""
    code: str  # e.g. "HASH_MISMATCH", "INCOMPATIBLE_KERNEL", "MANIFEST_INVALID"

# Generic loaded result (infra only)
@dataclass(frozen=True, slots=True)
class LoadedBundle:
    manifest: BundleManifest
    resource: Any  # opaque: dict (json), Path/handle (sqlite), etc. Handler decides.
    bundle_path: Path
    verified: bool
    warnings: tuple[str, ...] = ()

# Registry for genericity (add handlers, never modify loader)
BundleResourceLoader = Callable[[Path, BundleManifest], Any]  # root, manifest -> resource

class BundleLoader:
    def __init__(self, *, strict: bool = True, engine_version: str = "1.0.0") -> None: ...
    
    def register(self, bundle_format: str, handler: BundleResourceLoader) -> None: ...
    
    def load(self, bundle_path: str | Path) -> LoadedBundle:
        """Full lifecycle: resolve -> manifest validate -> compat -> integrity -> dispatch -> return."""
        ...

    # Context support for handles
    def __enter__(self): ...
    def __exit__(self, *exc): ...

# Convenience
def load_bundle(bundle_path: str | Path, *, strict: bool = True) -> LoadedBundle: ...
```

- Input: path to manifest file, bundle dir, or root containing payload+manifest.
- Output: LoadedBundle (manifest always attached for status/version/curation; resource opaque to loader).
- Errors: BundleLoadError only (never clinical EngineError here; caller maps if needed).

Reuse exactly: load_manifest, validate_manifest from manifest.py. No duplication.

## 2. Adapter / Handler Strategy (Genericity)

Loader core never modified for new types.

- `register("v1", v1_handler)` or `register("json-v1", ...)` 
- "v1" initial (matches current manifests bundle_format).
- Handlers live outside core (added in P0-4 for current resources; future Lance/Parquet separate).
- Handler example contract (infra, no medical):
  ```python
  def json_v1_handler(root: Path, manifest: BundleManifest) -> dict:
      # discover payload by convention (e.g. root / f"{manifest.bundle_id}.json" or sibling)
      payload = ...
      return json.loads(payload.read_text())
  ```
- SQLite handler returns opened handle or path (consumer does SQLiteReader etc).
- Discovery convention documented but not medical: relative to manifest dir using bundle_id or bundle_type hint.
- No ifs on "regimen" etc inside loader. Registry + format key only.

## 3. Lifecycle Contract (from Analysis, now binding)

Exactly:
1. Resolve (manifest + payload).
2. load_manifest + validate (reuse frozen).
3. Compatibility:
   - requires_kernel vs engine_version (major.minor compare; reject if manifest requires newer).
   - bundle_format registered/supported.
   - expiry/freshness (warn or reject per strict).
4. Integrity:
   - content_hash: compute (sha256: prefix + bytes of primary payload) == manifest.content_hash → reject on mismatch.
   - signatures: record (full verify later).
5. Dispatch: handler = registry[manifest.bundle_format]; resource = handler(root, manifest).
6. Return LoadedBundle(manifest, resource, path, verified=True, warnings=...).

Deterministic. No side effects beyond reads.

## 4. Compatibility + Integrity Rules

- requires_kernel: "1.0" compatible with "1.0.0" engine. "1.1" or "2.0" → BundleLoadError.
- bundle_format: exact match to registered key. "v1" baseline.
- content_hash verification mandatory (tamper reject per backlog DoD).
- curation_status, stats, source_refs: surfaced in manifest only (no interpretation).
- Production Guard (later): reads manifest.curation_status instead of raw json meta.
- I10 preserved: unknown fields dropped by load_manifest.

## 5. Feature Flag / Migration (P0-4/P0-5)

- P0-3: loader standalone. No engine change.
- P0-4: wrap current resources (diagnosis_index + clinical_constants + drug ref + sqlite + score) as sidecar manifests or bundle dirs. Use loader to load, pass resource to existing readers.
- Flag (e.g. in EngineConfig): use_bundle_loader: bool = False (default legacy direct).
- Coexist: both paths produce identical resource content.
- Rollback: flag=False exact prior.
- No change to BundleManifest, readers, providers, stages.

## 6. Definition of Done

- BundleLoader + LoadedBundle + BundleLoadError + register/load implemented.
- Registry strategy (generic).
- Full lifecycle per contract (compat + hash integrity + manifest reuse).
- "v1" handler baseline (or direct support) for JSON-like.
- Pure: no clinical/reader/provider/decision code.
- BundleManifest untouched.
- Errors clear, deterministic.
- Docs: this RFC + analysis.
- RFC_INDEX updated.

## 7. Acceptance Criteria

- Loader is pure infra: imports only stdlib + manifest.py. No clinical models, no antibiotic strings, no stage/reader code.
- load(manifest_example) succeeds, verifies hash (when payload present), returns manifest + resource.
- Tamper (bad hash) → BundleLoadError("HASH_MISMATCH").
- Incompatible requires_kernel → BundleLoadError.
- New bundle type: only register new handler; no edit to loader.
- Existing engine behavior identical (no calls to loader yet).
- Feature flag path (in P0-4) produces same output as direct.
- Production Guard can consume curation_status from LoadedBundle.manifest.
- Tests: infra only (no medical assertions; hash/compat/roundtrip/unknown format cases).
- 0 impact on frozen (manifest, P0-1 tests, P0-2 providers, invariants).
- After: freeze loader contract. Proceed to P0-4 without new RFC.

**Post-approval:** immediate impl per workflow. No further analysis. Update all handoffs at close. Repo sole source.

---

**End of RFC.** Contract only. Generic. Frozen after acceptance.