# ANTIBIO CURRENT PROJECT STATE
## VERSION 1.0

> **Status:** ADOPTED WITH AUDIT ADDENDUM — 2026-07-14.
> **Extends:** `ANTIBIO_PROJECT_CONSTITUTION.md` + `ANTIBIO_ENGINEERING_PLAYBOOK.md`.
> **Rule (from this doc):** Repository state is authoritative. If documentation and implementation
> disagree, implementation wins until documentation is synchronized. Priority order for truth:
> Repository → Code → Real execution → Documentation → Memory.
>
> The project owner supplied this document's body (below the addendum) verbatim and asked me to
> compare it to the repository and identify inconsistencies before adopting. Inconsistencies were
> found (see AUDIT ADDENDUM). Per this document's own ACKNOWLEDGEMENT section ("If none exist,
> adopt it"), the body is adopted as the *structural* project-state definition, but the
> discrepancies below are recorded and are being resolved by real execution rather than glossed
> over.

---

## AUDIT ADDENDUM (2026-07-14) — real-repository verification

Verified directly against `kb_p44.db` (SQLite) and `p44_kb_checkpoint.json` before adoption.
Findings, evidence-based, most material first:

1. **`kb_p44.db` was NOT a reproducible artifact.** At audit time it held **1836 objects**
   (Dose 1455, Evidence 184, Medication 99, Contraindication 76, Recommendation 13, Diagnosis 9),
   **138 open reviews**, **138 conflicts**, 3963 provenance rows — while its checkpoint recorded
   only **3** processed PDFs. The DB was an accumulation of many untracked/experimental runs, not
   a deterministic function of the corpus. This violates the platform mission (reproducible,
   auditable). **Action taken:** archived old DB → `kb_p44_ARCHIVED_accumulated_20260714.db`
   (preserved, not deleted); launched a clean full-corpus rebuild into a fresh `kb_p44.db`.

2. **`P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md` figures are stale/contradictory.** It variously
   claims 116 then 204 objects and "0 conflicts, 0 reviews." Neither matched the real DB. The
   report must be regenerated from the clean rebuild's measured output before P4.4 can be closed.

3. **Schema/model drift.** 204 of the 1836 objects had `knowledge_type = NULL` — the enhanced
   `KnowledgeObject` model was introduced mid-stream and older rows were never migrated. The clean
   rebuild produces a uniform schema. The real table is named `objects` (not `knowledge_objects`).

4. **Tooling defect (fixed).** `build_p44_kb.py` hardcoded the checkpoint path independent of
   `--db`, allowing checkpoint/DB drift (root cause of finding #1) and blocking independent/parallel
   builds. Fixed: checkpoint is now derived per-DB (`<db>.checkpoint.json`).

5. **Phase-label mismatch (documentation only).** This document labels P1=Terminology,
   P2=Clinical Data, P3=Semantic Extraction. The repository's `ROADMAP.md` labels P2=Eval &
   Assurance and P3=Clinical Data Curation (still ACTIVE: 101 diagnosis conflicts pending physician
   sign-off). Not a code issue; noted so the labels can be reconciled in a later doc-sync.

6. **Corpus count.** This doc says ≈193; the builder's real loader resolves **192** contributing
   PDFs from `knowledge_base.json`. Consistent with "≈".

**Conclusion:** P4.4 remains ACTIVE (not closed) until the clean rebuild completes and its real
numbers are audited into a regenerated report. Everything else in the body below is adopted.

---

This document extends

Project Constitution

Engineering Playbook

It represents the current production state
of the ANTIBIO repository.

Repository state is always authoritative.

If documentation and implementation disagree,
implementation wins until documentation is synchronized.

=========================================================
PROJECT MISSION
=========================================================

ANTIBIO is NOT an antibiotic calculator.

ANTIBIO is a production Clinical Knowledge Platform.

Primary mission:

Transform Russian Ministry of Health Clinical Recommendations

↓

Production Knowledge Objects

↓

Deterministic Clinical Decision Support

↓

Future AI Platform

Everything must remain

traceable

deterministic

versioned

auditable

=========================================================
CURRENT ARCHITECTURE
=========================================================

Current production pipeline

PDF

↓

PyMuPDF

↓

MinerU (OCR fallback)

↓

Docling

↓

DocLayout-YOLO

↓

Table Transformer

↓

RapidTable

↓

Unified Document Model

↓

Semantic Layer

↓

Knowledge Layer (current milestone)

↓

Clinical Decision Engine

↓

Application

=========================================================
CURRENT STATUS
=========================================================

P0 — Infrastructure — COMPLETE

P1 — Terminology — COMPLETE

P2 — Clinical Data — COMPLETE

P3 — Semantic Extraction — COMPLETE

P4.1 — Multi Engine Extraction — COMPLETE (Verified)

P4.2 — Layout Foundation — COMPLETE (Verified)

P4.3 — Medical Semantic Layer — COMPLETE (Verified)

P4.5 — Layout Intelligence Platform — COMPLETE (Verified)
  (DocLayout-YOLO, Table Transformer, RapidTable, Structured Tables,
   Cell Provenance, Production Reprocessor, Benchmark, Production Audit)

CURRENT ACTIVE MILESTONE — P4.4 — Production Knowledge Base

=========================================================
VERIFIED COMPONENTS
=========================================================

Production verified: PyMuPDF, MinerU, Docling, DocLayout-YOLO, Table Transformer, RapidTable,
Unified Document Model, Semantic Layer, Layout Layer, Production Reprocessor, Checkpoint/Resume,
Structured Tables, Cell Provenance.

=========================================================
KNOWN PRODUCTION TOOLS
=========================================================

Production Reprocessor, Checkpoint, Resume, Metrics, Corpus Validation, Production Audit,
Regression Suite.

=========================================================
KNOWN CORPUS
=========================================================

Current production corpus ≈193 Clinical Recommendation PDFs (real loader: 192).
Primary repository: Russian Ministry of Health clinical recommendations. Corpus is production data.

=========================================================
CURRENT ENGINEERING STRATEGY
=========================================================

Never implement isolated features. Every implementation must complete an entire production
subsystem. Sequence: Design → Implementation → Migration → Testing → Benchmark → Production
Validation → Engineering Audit → Documentation Sync → Milestone Closure.

=========================================================
CURRENT DOCUMENTATION
=========================================================

ROADMAP, PROJECT_STATE, NEXT_TASK, DECISIONS, AI_LOG, AGENTS, Architecture / Extraction /
Semantic / Knowledge documentation. Must remain synchronized.

=========================================================
CURRENT QUALITY POLICY
=========================================================

Every milestone requires real execution, real corpus, real benchmarks, real regression, real
production audit. No mocked execution.

=========================================================
CURRENT FROZEN COMPONENTS
=========================================================

Clinical Decision Engine, Medical recommendations, Deterministic treatment logic, Approved medical
content, Bundle schemas. Not modified without explicit approval / RFC.

=========================================================
CURRENT DEVELOPMENT TARGET
=========================================================

Active milestone: P4.4 Production Knowledge Base. Create: Immutable Knowledge Objects, Versioning,
Source Lineage, Validation, Deduplication, Conflict Detection, Merge Engine, Review Queue, Impact
Analysis, Production Persistence, Knowledge Audit. Do NOT redesign completed milestones — extend
the existing architecture.

=========================================================
KNOWN PROJECT PHILOSOPHY
=========================================================

Extraction → Layout → Semantic → Knowledge → Clinical Decision Engine → Application.
Every layer has exactly one responsibility. Never bypass architecture.

=========================================================
WHEN UNCERTAINTY EXISTS
=========================================================

Priority order: Repository → Code → Real execution → Documentation → Memory.

=========================================================
EXPECTATION
=========================================================

Continue developing ANTIBIO autonomously within this architecture. If a required subsystem does
not exist: design, implement, test, benchmark, document, integrate. Implementation is expected —
do not ask whether it is allowed. Stop only for: repository mismatch, medical ambiguity, or
explicit user request. Otherwise continue autonomously.
