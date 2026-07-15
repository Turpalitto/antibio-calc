# MIGRATION_PLAN_NORMALIZED_REGIMENS.md
## Migration — normalized_regimens.sqlite → assembled ClinicalRegimens · P5.1
## Status: PROPOSED (design only — no migration executed, no code, no DB change)

> The concrete migration from the engine's current source (`normalized_regimens.sqlite`, 2,675 rows)
> to assembled `ClinicalRegimen` objects, without breaking the frozen Clinical Decision Engine.
> This is the P5.1-specific refinement of P5.0's `KNOWLEDGE_PLATFORM_MIGRATION_RFC.md` — same
> additive, shadow-validated, config-cutover discipline, applied to the regimen layer specifically.

## 0. Non-negotiable constraint
The engine must, at every step until an explicit config cutover, keep reading exactly what it reads
today (`normalized_regimens.sqlite` via `RegimenProviderAdapter`). Nothing below modifies that path
until Step 5, and Step 5 is reversible by config.

## Step 1 — Equivalence baseline (measure before moving anything)
Establish, read-only, the ground truth the migration must preserve:
- Snapshot the current 2,675 `normalized_regimens` rows and every `RecommendationCandidate` the
  engine currently produces for the golden-case query set (`clinical_engine/golden_cases/`).
- **Check MR-5 directly:** query `review_status`/`reviewed_by`/`approved` — record which rows carry
  real human approvals that MUST survive. (This is the single most important pre-migration fact;
  losing approvals = repeating clinical validation work = unacceptable.)
- Record the performance baseline (MR-3): current `Engine.recommend()` latency distribution.
None of this is designed here beyond "it must happen first" — it is measurement, not architecture.

## Step 2 — Dual assembly (additive; old path untouched)
Run the Regimen Assembly Engine (`REGIMEN_ASSEMBLY_ENGINE_RFC.md`) to produce `ClinicalRegimen`
objects into the canonical store, ALONGSIDE the live `normalized_regimens.sqlite`. Two sub-decisions
(deferred from `KNOWLEDGE_TO_REGIMEN_PIPELINE.md` §5), to be settled here at execution time:
- **Source of regimens for v1:** because rule-based table yield is low today (CKY.tables=1.1%),
  the pragmatic v1 assembly source is the LLM pipeline's already-validated regimens
  (`metadata.sqlite::antibiotic_regimens`, 2,675 validated), mapped into `ClinicalRegimen` via
  `medical_normalizer` as a library — NOT a from-scratch rule-based reassembly that would currently
  under-yield. The kb_p44 atomic-fact assembly path is built in parallel and blended in as its
  table yield improves (RC-009 fix), field by field, with provenance recording the source.
- **Approval carry-forward:** where a new `ClinicalRegimen` is provably field-equivalent to an
  already-`approved` `normalized_regimens` row (same guideline_id/regimen_id, identical clinical
  fields), carry the approval + reviewer + date forward (Gate 5). Non-equivalent or new regimens
  start at `review_status=pending` (Validation Gates RFC).

## Step 3 — Parity harness (dual-read, zero production impact)
For the golden-case query set AND the full 2,675-regimen space, run both providers
(`RegimenProviderAdapter` on old data, `CanonicalStoreRegimenProvider` on assembled regimens) and
diff the resulting `RecommendationCandidate` sets field-by-field. Also run the free cross-check from
`KNOWLEDGE_TO_REGIMEN_PIPELINE.md` §4 (assembly provenance vs. `clinical_engine/corpus/provenance.py`).
Log every divergence with full context. Engine production path stays on the old provider throughout.

## Step 4 — Divergence adjudication (no silent acceptance)
Every divergence is classified:
- **Assembly defect** → fix the assembly ruleset (versioned), re-run.
- **Genuine data-quality improvement** (assembled regimen is correctly better — e.g. carries
  evidence_level the old row lacked, or a structured contraindication) → document + physician-review
  per `CLINICAL_VALIDATION_FRAMEWORK.md`, do not auto-accept.
- **Old-data artifact** (old row had a defect) → record; the improvement is intentional.
Exit gate for Step 4: zero UNEXPLAINED divergence on the full golden dataset (once authored to the
500+ scale — MR-7), every explained divergence signed off.

## Step 5 — Config cutover (reversible)
Flip `EngineConfig`'s provider selector from `RegimenProviderAdapter` to
`CanonicalStoreRegimenProvider` (a configuration change, per `CLINICAL_ENGINE_ADAPTER_RFC.md` §Phase-3
constraint). The engine code, spec, and behavior are unchanged — only its data source. Rollback =
flip the selector back; old files remain intact through the compatibility window.

## Step 6 — Compatibility window & retirement (later, separate decision)
Keep `normalized_regimens.sqlite` + `build_normalized_sqlite.py` intact but unused for N clean audit
cycles (measured, not calendar-dated). Only after clean cycles: demote `normalized_regimens.sqlite`
to a generated projection (rebuilt from canonical) or retire it. `metadata.sqlite::antibiotic_regimens`
and the `medical_normalizer` library are NOT retired — they become permanent ingestion staging + a
reused normalization library respectively.

## Rollback summary
| Step | Rollback | Data at risk |
|---|---|---|
| 1 | N/A (read-only measurement) | none |
| 2 | discard assembled regimens; old path is authoritative | none (dual, old primary) |
| 3 | stop the harness; nothing was routed to callers | none |
| 4 | continue on old path while fixing | none |
| 5 | config flip back to old provider | none (old files intact) |
| 6 | only irreversible step — gated behind N clean cycles + explicit decision | old serving file (kept until this step) |

## Exit criteria (this migration is DONE / RC-019 closable)
- Engine serves exclusively from assembled `ClinicalRegimen` objects in production (config cutover
  done, one clean post-cutover audit cycle passed).
- 100% golden-case parity; all divergences explained + signed off.
- No approval lost (Step 1 approvals all carried forward or re-reviewed with justification).
- No performance regression vs. the Step 1 baseline.
- `normalized_regimens.sqlite` is either retired or demoted to a generated projection (no longer an
  independent source of truth).
- Provenance cross-check (assembly vs. corpus resolver) clean across the corpus.
- `ROOT_CAUSE_REGISTER.md` RC-019 updated to Fixed with this evidence.

## Honest unknowns carried from P5.0 (not re-guessed here)
Whether real approvals exist in `normalized_regimens.sqlite` (Step 1 resolves this — MR-5); the
performance baseline (Step 1 — MR-3); whether the engine is in live production use (affects how
much of the shadow/parity apparatus is strictly needed — MR-8); `medical_normalizer`'s frozen-scope
interpretation for reuse as a library (MR-4). These are resolved by measurement/owner-decision at
execution time, not by architectural assertion.
