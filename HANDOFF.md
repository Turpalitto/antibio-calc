# HANDOFF.md — ANTIBIO (Cross-IDE / Cross-AI Onboarding)

## Current handoff — 2026-07-30

P5.6 is in ACCEPTANCE but NOT COMPLETE. Credential rotation is closed by
owner attestation; the historical fresh-clone gate passed. C7 source-fidelity
review is closed at 182 events / 113 regimens / zero validation issues.
Proposed-boundary canonical tests: 1499 passed, 11 skipped, 1 xfailed,
0 failed (1511 collected).
The exact C7/audit boundary is committed as `60e6033`; its committed tree
matches the isolated validated tree. Remaining P5.6 blockers are a
locked-dependency fresh-clone verification of that commit and publication:
`main` is ahead of `origin/main`. Review Workbench is local-only
and Clinical Engine remains disconnected. P6 is BLOCKED.
Read `GOVERNANCE_SOURCE_OF_TRUTH.md`, `P5.6_PRODUCTION_RECOVERY_REPORT.md`,
then `NEXT_TASK.md`.

**Purpose:** Central entry point. Onboard by reading this + all referenced docs. Repository is single source of truth. Chat history = 0.

**⚠️ GOVERNANCE — adopted 2026-07-14. All governing docs now live in `docs/governance/`.**
Read **`docs/governance/AUTONOMOUS_ENGINEERING_KERNEL.md` first** — it is the single master entry
point and points to the six governing documents (Constitution, Engineering Playbook, Current
Project State, AI Operating System, Clinical Governance, Repository Intelligence), read in that
order. These supersede the old Reviewer-only role in AGENTS.md §0.1. Frozen technical scope
unchanged. Prioritized debt lives in `TECH_DEBT_BACKLOG.md`. To start work: "Read
`docs/governance/`, adopt them as governing documents, continue with the active milestone."
Then continue with the state/plan docs below.

**Onboarding Steps (mandatory):**
1. Read this HANDOFF.md.
2. Read the four governance docs above, then every document referenced below.
3. Confirm understanding by explicitly reporting (onboarding not complete until you do):
   - Frozen Components
   - Current Milestone
   - Active Issue
   - Workflow Stage
   - Current Test Status
   - Next Implementation Step
4. If any item cannot be determined from docs, stop and ask before any code.
5. Wait for project owner approval before implementation.

**Example Report (use this format):**
Frozen Components: [list as in PROJECT_STATE: Architecture v3, BundleManifest+schema/validator, Provider Ports, Bundle Loader, Engine invariants, Medical Normalizer, SQLite, Dictionary, Trace/Opt/Evidence rules, P1-A/B]
Current Milestone: P2-1 Conformance Validator COMPLETE + FROZEN
Active Issue: P2-1 CLOSED (additive)
Workflow Stage: P2-1 full workflow (Analysis+RFC+Impl+real tests 298p+Review PASS+Freeze+Docs). 
Current Test Status: clinical_engine 299 passed 0 failed (incl MANIFEST_VALIDATION_ERROR negative). Relevant green. The frozen Bundle Loader received an RFC-approved additive extension while preserving default behavior and compatibility.
Next Implementation Step: P2-1 done. P2-2 Analysis ONLY. STOP. No impl.

**Date:** 2026-07-10

## Required Reading (start here)
1. SESSION_SUMMARY.md
2. PROJECT_STATE.md
3. NEXT_TASK.md
4. DECISIONS.md
5. Current RFC (see RFC_INDEX.md for active one)

## 1. Project Overview
ANTIBIO is a clinical decision support system for antibiotic therapy, built from Russian Ministry of Health clinical guidelines (КР МЗ РФ).

## 1. Project Overview
ANTIBIO is a clinical decision support system for antibiotic therapy, built from Russian Ministry of Health clinical guidelines (КР МЗ РФ).

Core products:
- Clinical Decision Engine (deterministic 10-stage Python kernel)
- HTML calculator (antibiotic_calc.html) for dose calculation
- Knowledge extraction pipeline (PDF → normalized regimens)

Goal: Provide structured, normalized, safe, provenance-traced antibiotic recommendations from evidence-based guidelines. Offline-first, reproducible, doctor-support (not decision maker).

## 2. Current Architecture (v3 — FROZEN)
**Ports & Adapters + Knowledge-as-Data**

- **Execution Kernel** (frozen v1): Pure function `(PatientQuery + KnowledgeSnapshot + Config) → RecommendationSet`. 10 stages. Deterministic. No I/O, no network at runtime.
- Knowledge comes as **versioned immutable bundles** (RegimenBundle, SafetyBundle, etc.).
- Readers (low-level) behind **Provider ports** (P0-2 in progress).
- Variability in data/bundles, not in kernel code.
- Governance via curation status + Production Guard.

**Never:**
- Parse PDFs in engine
- Mutate state
- Default UNKNOWN to MODERATE
- Silently exclude
- Change frozen models without RFC

See `ARCHITECTURE_V3.md` for full layers and principles (P1–P12).

## 3. Development Philosophy & Rules
- **Architecture v3 FROZEN**. No redesign.
- **BundleManifest (P0-1) FROZEN** (including schema and validator API).
- **Workflow (mandatory):** RFC → Implementation → Acceptance Review → Freeze → Backlog Closed.
- **Agent role:** Follow backlog strictly. For P0-2+ implementation per spec. Use Reviewer/QA mindset where appropriate.
- **Measure first.** Tests, coverage, determinism, safety invariants before claiming done.
- **No feature creep.** Only backlog items.
- **Update handoff docs** at end of every task (AI_LOG, PROJECT_STATE, NEXT_TASK, DECISIONS).
- **Single source of truth:** These MD files + frozen specs. Chat history does not count.

**What MUST NEVER change without new RFC:**
- Architecture v3
- BundleManifest contract / schema / validator
- Extraction / Normalizer / SQLite schema / Medical Dictionary
- Engine invariants (see `tests/test_invariants.py` and spec §12)
- Frozen models and public contracts

## 4. Completed Phases / Milestones
- M1–M8: Engine core (models, readers, 10 stages, safety, ranking, trace) — DONE
- M9: Independent audit remediation — DONE
- M10–M13: Data quality audit, governance infra, release readiness, Production Guard — DONE
- P0-1: BundleManifest Specification — **CLOSED + FROZEN** (2026-07-10)
  - Schema + validator + examples + full test coverage (including negatives + I10)
  - 1159 tests green overall (1 pre-existing xfailed)
- P0-2 Provider Ports — **CLOSED + FROZEN** (2026-07-10)
  - Lightweight RFC + adapters (Regimen/DrugSafety/DiagnosisProvider) wrapping readers 100%.
  - Flag + DI + stage migration complete. Equality proven by test. Legacy coexist.
  - See P0-2_Implementation_RFC.md . No behavior change.
  - Full handoff + audit performed.
- P0-1 to P0-4 — **COMPLETE + FROZEN**.
- See P0_COMPLETION_REPORT.md.
- Process complete. No new rules. P1-A COMPLETE + FROZEN. P1-B: CLOSED (ACCEPTED + FROZEN genuine). P0 fixture restored, P1 dedicated. Only P1 tests updated. 0 fail + Golden + no reg + neg prove.

## 5. Current Milestone & Active Task
**Phase:** P2-1 COMPLETE + FROZEN (additive). Full workflow done. Next roadmap item: ANALYSIS ONLY.

**P0 COMPLETE + FROZEN.**

**Active / Next:** P1-B CLOSED ACCEPTED FROZEN. Next: P2 Analysis only. STOP.

No P0 changes without RFC.

**Frozen Components (from docs):** Architecture v3, BundleManifest + schema/validator, Provider Ports, Bundle Loader, Engine invariants, Medical Normalizer, SQLite schema, Medical Dictionary, Clinical Traceability/Optimization/Evidence rules.

**Current Milestone:** P3 Clinical Data Curation

**Active Issue:** Diagnosis index conflicts (101), renal structure, synonyms expansion, ATC fill, Golden Cases volume.

**Workflow Stage:** Engineering frozen (9.8/10). Medical content curation phase. Physician-driven. No engine changes.

**Current Test Status:** clinical_engine 302 passed. Golden framework now supports proper exclusion proof.

**Next Implementation Step:** Curate data to PRODUCTION_CURATED. Expand synonyms. Structure renal. Build large Golden set. Update handoffs only.

## 6. Immediate Next Task (P0-2)
See dedicated `NEXT_TASK.md`.

## 7. Common Mistakes to Avoid
- Treating chat history as source of truth.
- Proposing architecture changes or "improvements" to frozen items.
- Implementing without updating handoff docs.
- Bypassing workflow (no RFC → no work on contracts).
- Assuming "unknown" data is safe (Invariant #13 and safety rules).
- Mutating dataclasses (use `dataclasses.replace`).
- Adding features not in backlog.

## 8. Coding Rules (from specs + AGENTS)
- Frozen dataclasses + slots.
- Pure stages, no I/O.
- Determinism invariant.
- Safety is hard gate, orthogonal to ranking.
- Tests must cover invariants (see `test_invariants.py`).
- Production Guard respects curation status.
- Update AI_LOG + PROJECT_STATE + NEXT_TASK + DECISIONS after every task.

## 9. Review Process
1. Design (or read existing spec)
2. Review (if new RFC)
3. Implementation
4. Tests (including negatives + invariants)
5. Code Review
6. Documentation (update handoff package)
7. Merge

## 10. Definition of Done (per backlog)
- All acceptance criteria met
- 0 regression on full test suite
- Invariants green
- Documentation updated
- Handoff package consistent

## 11. Acceptance Workflow
RFC (if needed) → Impl → Acceptance Review → Freeze → Close in backlog.

## 12. Key Frozen Items (2026-07-10)
- BundleManifest (P0-1)
- Architecture v3
- Engine v1 kernel
- Medical Normalizer
- Extraction layer
- SQLite schema
- Versioning model (schema_version + version + requires_kernel + bundle_format)
- I10 Forward Compatibility

## 13. Where to Start (for new AI)
1. Read this HANDOFF.md
2. Read `ARCHITECTURE_STATUS.md`
3. Read `NEXT_TASK.md`
4. Read `PROJECT_STATE.md`
5. Read relevant spec: `docs/superpowers/specs/clinical-decision-engine-v1.md`
6. Run: `python -m pytest -q` (should be green)
7. Look at `clinical_engine/readers/` for current reader interfaces (P0-2 target)

## 14. Quick Commands
- Full tests: `python -m pytest medical_normalizer/tests clinical_engine/tests src/tests -q`
- Engine smoke: via golden runner or test_engine
- See `README.md` for more.

**This document + the 8 listed handoff files are the complete context. Do not rely on anything else.**
