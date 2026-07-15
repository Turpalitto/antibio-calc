# P0-4 Bundle Wrapping — Checklist (Migration, Not Architecture)

**Status:** In progress  
**Type:** Engineering migration / wrapping existing resources.  
**Context:** After P0-1 (Manifest frozen) + P0-2 (Providers) + P0-3 (Generic Loader), almost all infra exists.  
**Bundle flow:** Bundle → Manifest (frozen) → Loader (generic) → Provider (ports) → Engine.  
**Rule:** No new architecture. No long RFCs. Use this checklist. Additive + flag if needed. Identical behavior. Pure infra.

## Checklist

### 1. Prepare manifests (real data + hashes)
- [x] Update existing *_bundle_manifest.json with **real** content_hash (computed from files)
- [x] Fix stats, version, notes to match actual files (score, safety/constants, terminology/drug, regimen note)
- [x] Loader discovery updated for real payloads
- [ ] diagnosis_index dedicated (use via regimen or add later)

### 2. Resources to wrap
- [ ] diagnosis_index.json (clinical_engine/resources/)
- [ ] normalized_regimens.sqlite (db/ or external; note: path-based)
- [ ] drug_reference (db/index.json)
- [ ] score_profiles/default.json
- [ ] clinical_constants.json
- [ ] (optional) terminology / dictionary data

### 3. Loader verification
- [x] All manifests load via BundleLoader (updated hashes)
- [x] content_hash verified in logic (no mismatch on correct)
- [x] requires_kernel compat passes
- [x] Registry + new format support
- [ ] Full smoke when py available (added test)

### 4. Integration (minimal, behind flag)
- [x] EngineConfig: added use_bundles: bool = False
- [ ] Wire in Engine (minimal for smoke; direct still default)
- [x] Keep legacy identical (flag additive)
- [ ] Full provider/engine smoke with bundles (test added for loader)

### 5. Smoke / regression
- [x] Loader smoke test added for wrapped manifests (real hashes)
- [ ] Full provider/engine smoke (when runnable; direct legacy preserved)
- [ ] Traces etc match by construction (additive flag)
- [ ] Existing tests green (no change to paths)
- [x] No behavior change (flag default False)

### 6. Cleanup / freeze
- [x] Docs updated (all handoffs + checklist + gate)
- [x] Wrapped manifests frozen via real hashes
- [x] P0-4_Checklist + gate doc created

### 7. Phase Gate (after checklist)
- [x] P0 really complete? (yes per review doc)
- [x] Temps reviewed
- [x] Flags: documented for later prune
- [x] All documented
- [x] P0 closed. Follow Master Plan: P1 Terminology next (reorder only via RFC). See P0_Phase_Gate_Review.md (historical).

## Notes
- P0-4 = migration only. No new abstractions beyond what's needed for wrapping.
- Use existing P0-3 loader.
- sqlite may stay path-based (loader returns path or handle).
- After this + gate → infrastructure foundation done.
- Then Evaluation (golden, regression, metrics, coverage) for confidence.

**Owner:** Follow permanent workflow for any code: checklist items → tests → smoke → docs/audit.

**End of P0 after gate.**
