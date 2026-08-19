# SESSION_SUMMARY.md — ANTIBIO Executive Handoff (2-3 min read)

## Current session — 2026-07-15

P5.6 recovery implemented and validated. New local Review Workbench holds 1,556 ClinicalRegimen, 652 TherapeuticOption, and supporting review populations; total 9,153, all PENDING. Production KB and normalized DB hashes unchanged. Full pytest 1,373 collected / 1,371 passed / 0 failed. P5.6 cannot close until credential rotation and Git recovery; P6 remains blocked.

**For any AI/IDE starting fresh. Current truth as of 2026-07-10.**

## What is ANTIBIO?
Clinical decision support for antibiotics, derived strictly from Russian Ministry of Health clinical guidelines (КР).

Two main deliverables:
1. Deterministic Clinical Decision Engine (Python) — takes patient query → ranked safe recommendations.
2. Supporting HTML calculator (antibiotic_calc.html).

Everything is **knowledge-as-data**: guidelines become versioned bundles. Kernel is frozen and deterministic.

## Current State (High Level)
- **Architecture v3 + Engineering Master Plan** — FROZEN and accepted.
- **P0-1 to P0-4** — **COMPLETE + FROZEN**.
- See P0_COMPLETION_REPORT.md.
- Process complete. No new rules.
- P1-A COMPLETE + FROZEN. P1-B CLOSED (ACCEPTED + FROZEN genuine post review).
- P2-1 Conformance Validator: COMPLETE + FROZEN (additive, 298 clinical tests real green).
- Engine core done.
- Relevant tests: clinical_engine 299 passed 0 failed (MANIFEST_VALIDATION_ERROR negative added). The frozen Bundle Loader received an RFC-approved additive extension while preserving default behavior and compatibility.

**Onboarding:** Read HANDOFF.md + refs. Onboarding complete only after explicitly reporting the 6 items (Frozen Components, Current Milestone, Active Issue, Workflow Stage, Current Test Status, Next Implementation Step). If unclear, stop.

**Clinical Traceability Rule (law):** 7 questions per rec. No black box. Clinical value primary.

**Optimization Rule (permanent):** Never optimize infrastructure unless it directly improves clinical decision quality, safety, maintainability, or measurable performance.

If no measurable benefit exists, do not change it.

## Frozen (Do Not Touch)
- Architecture v3
- BundleManifest contract, schema, and validator API
- Extraction / Medical Normalizer / SQLite schema / Medical Dictionary
- Engine invariants (see test_invariants.py)
- Version model: schema_version (structure) + version (content) + requires_kernel (engine compat) + bundle_format
- I10: ignore unknown optional fields

## Key Principles (Memorize)
- Determinism (same input → same output)
- Safety is hard gate (orthogonal to ranking). Unknown ≠ safe.
- Once excluded → forever excluded (excluded list only grows)
- Provenance to source quote
- Curation status is a real gate (Production Guard)
- Kernel frozen; variability in data

## Current Workflow (Mandatory)
RFC (if needed) → Implementation → Acceptance Review → Freeze → Backlog Closed

## Next Task (post P2-1)
P2-1 COMPLETE + FROZEN. Handoff done. Onboard next roadmap item: ONLY Analysis. STOP. See DEVELOPMENT_BACKLOG for queue.

See `NEXT_TASK.md`, `DEVELOPMENT_BACKLOG.md`, `PROJECT_STATE.md`.

## How to Verify You're on Track
1. Run full tests: should stay green.
2. Check invariants pass.
3. Any change to frozen items → new RFC required.
4. Update AI_LOG.md + PROJECT_STATE.md + NEXT_TASK.md + DECISIONS.md at end of task.
5. Keep this handoff package consistent.

## Where the Truth Lives (Read These First)
- `HANDOFF.md` (this level + links)
- `ARCHITECTURE_STATUS.md`
- `PROJECT_STATE.md`
- `NEXT_TASK.md`
- `ARCHITECTURE_V3.md`
- `ENGINEERING_MASTER_PLAN.md`
- `DEVELOPMENT_BACKLOG.md`
- `clinical-decision-engine-v1.md` (in docs/superpowers/specs/)

**Everything else is detail or historical. Start here.**

**P0-1 is closed. Do not reopen BundleManifest questions.** Focus on executing the next backlog item.
