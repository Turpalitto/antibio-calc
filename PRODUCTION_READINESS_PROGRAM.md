# ANTIBIO — Production Readiness Program (PRP)
## VERSION 1.0 · STRICT MODE

> **Goal:** transform the repository into a **Production Release Candidate**. Not a bug hunt, not a
> cleanup — a governed, *iterative* program: discover → fix / justify / defer / track → test →
> doc-sync → re-scan. Repeat until only consciously-accepted limitations remain.
> **Governed by** `docs/governance/` (repository-first, real execution only, frozen scope
> untouched without RFC). **Iteration model** (per owner): each cycle fixes a batch, verifies it,
> updates docs, then re-scans — never one giant pass.
>
> **Concurrency rule:** CPU-bound phases (regression Phase 13, performance Phase 7) do **not** run
> while the P4.4 layout rebuild is active — they would contend and produce invalid numbers. They
> are queued for after the rebuild. Read-only discovery/audit runs now.

---

## Phase status

| # | Phase | Status |
|---|-------|--------|
| 1 | Full Repository Discovery | DONE (2026-07-14, iter 0) |
| 2 | Architecture Audit | IN PROGRESS |
| 3 | Code Audit | IN PROGRESS |
| 4 | Test Audit | PENDING (needs suite run → after rebuild) |
| 5 | Documentation Audit | IN PROGRESS (governance done; report drift tracked) |
| 6 | Security Audit | PENDING |
| 7 | Performance Audit | QUEUED (after rebuild — CPU) |
| 8 | Clinical Safety Audit | IN PROGRESS (tables=0 investigation) |
| 9 | Corpus Audit | IN PROGRESS (clean rebuild running) |
| 10 | Tooling Audit | IN PROGRESS |
| 11 | Technical Debt | ACTIVE (`TECH_DEBT_BACKLOG.md`) |
| 12 | Remediation | ACTIVE (iterative) |
| 13 | Regression | QUEUED (after rebuild — CPU) |
| 14 | Engineering Review | PENDING |
| 15 | Production Acceptance | PENDING |

---

## Phase 1 — Repository Discovery (measured 2026-07-14)

**Code:**
- 202 Python files (excl. caches). Packages: `src/pipeline` (18) + `src/pipeline/extraction` (12),
  `medical_normalizer` (13), `clinical_engine` (9), `src/llm` (+providers 10), `medical_dictionary` (2).
- Core entry points (compile-clean): `main.py`, `production_reprocessor.py`, `build_p44_kb.py`,
  `reprocess_p45_layout.py`, `validate_full_corpus.py`.

**Tests:** 54 test files across 3 suites (`clinical_engine/tests`, `medical_normalizer/tests`,
`src/tests`). Documented baselines (unverified this session): medical_normalizer 823, clinical_engine
~299–302, src/tests 39, full ~1266.

**Config/build:** `pyproject.toml`, `.gitignore`, `build_html.ps1`, `server.js`,
`config/document_processing.yaml`. **No CI** (`.github/` absent) → PRP finding PR-SEC/OPS.

**Frozen (do not modify without RFC):** `clinical_engine/`, approved medical content,
deterministic treatment logic, bundle schemas, `medical_normalizer/` core, `db/schema.json`.

---

## Findings register

Severity: **BLOCKER** (blocks release) · **HIGH** · **MED** · **LOW**. Status: OPEN / FIXED /
DEFERRED / TRACKED.

| ID | Sev | Phase | Finding | Status |
|----|-----|-------|---------|--------|
| PR-001 | BLOCKER | 8/9 | **FIXED + VERIFIED 2026-07-14.** Root cause: `layout.py::_extract_table_with_transformers` referenced `tbbox` (line ~266) before assigning it (line ~270) → `NameError` on every detected table, swallowed by bare `except: pass` (line ~282) → ALL structured tables dropped → KB 100% flat text. Proven by `diagnose_pipeline.py` stage tracer on Сепсис новорождённых.pdf (before: structured_tables=0, table-sourced=0, kb table_row=0). Fix: compute `tbbox` before use; removed duplicate; made the two swallow-points log (observability). After: structured_tables=**29**, table-sourced entities=**4**, kb provenance table_row=**4**, verdict "OK". Regression tests added (fast + real). | FIXED |
| PR-002 | HIGH | 9/11 | kb_p44.db was a non-reproducible accumulation (TD-001). Clean rebuild running. | IN PROGRESS |
| PR-003 | HIGH | 3/11 | KnowledgeObject schema drift, no migration tool (TD-002: 204 NULL knowledge_type). | OPEN |
| PR-004 | MED | 10/11 | Repo-root clutter: 24 `_*.py`/`temp_*.py` throwaway probes + 19 logs + 12 json + 3 DBs (TD-004). | OPEN |
| PR-005 | MED | 5/11 | Milestone doc drift; no automated consistency gate (TD-006/007). | OPEN |
| PR-006 | MED | 6 | No CI pipeline (`.github/` absent) — no automated test/regression gate. | OPEN |
| PR-007 | LOW | 10 | Overlapping knowledge DBs at root, unclear authority (TD-005). | OPEN |
| PR-008 | MED | 8 | Low table-entity yield (29 tables → 4 objects on Сепсис). **Scope (owner 2026-07-14): not just "how much" but "WHY every candidate is lost" — classify each into exactly ONE reason (Accepted / Duplicate / Deduplication / Knowledge Builder unsupported / Normalization failed / Validation failure / Confidence threshold / Unsupported entity type / Parser failure / Other) and produce a ranked loss histogram that becomes a PERMANENT benchmark.** Tool built (`semantic_yield_audit.py`), classifier mirrors real production decision points. Runs after rebuild → drives which PR to open next. | OPEN (tool ready) |

*(Register grows each iteration. Code/security/perf audits will add IDs.)*

---

## Iteration log

### Iteration 0 (2026-07-14) — program bootstrap + discovery
- Created this program doc. Ran Phase 1 discovery (real census above).
- Seeded findings register from measured evidence + existing `TECH_DEBT_BACKLOG.md`.
- Identified **PR-001 (tables=0)** as the top candidate BLOCKER — investigating the
  layout → `doc.structured_tables` path next.
- Regression/perf deferred until the P4.4 rebuild finishes (CPU concurrency rule).

### Iteration 1 (2026-07-14) — PR-001 investigation (top BLOCKER)
- Traced layout→KB path. Verified via live DB query: **0/2613** provenance rows have any table
  origin. Confirmed the running rebuild is producing a **flat-text-only** KB despite paying full
  layout CPU cost (2-6 min/PDF).
- **Strategic fork raised to owner** (conflicting-requirements stop condition): the layout-heavy
  rebuild delivers no table value. Options: (A) pause rebuild, fix PR-001, one correct rebuild;
  (B) let flat-text baseline finish, fix + re-enrich after; (C) accept flat-text KB for P4.4, treat
  tables as P4.4.1. Recommendation: **A** (root-cause first, avoids two multi-hour wasteful runs).
- Awaiting decision before killing/altering the running build.

### Iteration 2 (2026-07-14) — PR-001 root cause fixed + verified (owner: "fix root cause first")
- **Stopped** the flat-text rebuild (per owner instruction).
- Built reusable stage tracer `src/pipeline/extraction/diagnose_pipeline.py` (PDF→Layout→Doc→
  Semantic→KO→SQLite, reports counts per stage + surfaces swallowed layout exceptions).
- **First loss point proven = Stage 1 (Layout).** `NameError: tbbox` on every detected table,
  swallowed by bare `except: pass`. Downstream (semantic→KB) plumbing was correct all along.
- **Root-cause fix only** (`layout.py`): compute `tbbox` before use; removed duplicate assignment;
  converted two silent `except: pass` to `logger.warning` (observability, so this class of silent
  failure cannot recur).
- **Verified by real re-run** on the same PDF: structured_tables 0→29, table-sourced entities 0→4,
  KB provenance table_row 0→4. Verdict: "OK: table-origin provenance reaches the Knowledge Base."
- **Regression tests** `src/tests/test_layout_table_provenance.py`: fast deterministic
  (table cell → SQLite table_row, no models, 8s, PASS) + real (layout on table-heavy PDF yields
  >0 tables, 143s, PASS).
- New follow-up finding **PR-008** (low table-entity yield) logged — not a blocker.
- **Next:** full corpus rebuild may now resume (step 7) on the fixed pipeline into a fresh DB.

### Iteration 3 (2026-07-14) — rebuild on fixed pipeline + PR-008 gate armed
- Full corpus rebuild relaunched on PR-001-fixed pipeline into fresh `kb_p44.db` (flat-text partial
  archived as `kb_p44_FLATTEXT_prePR001fix_20260714.db`). **PR-001 validated at corpus scale:**
  table_row provenance accumulating in real DB (0 → 6+ across first 7 PDFs).
- Built reusable **PR-008 audit tool** `src/pipeline/extraction/semantic_yield_audit.py` — measures
  the table→KO funnel (tables → cells → len-filter → entities → post-dedup → KB-accepted → table
  provenance) + reports entity types dropped by the KB builder's type gap.
- **Gate set (owner directive):** P4.4 must NOT close until PR-008 quantifies table-derived yield
  and confirms acceptable clinical value. Suspected choke points to quantify: `DRUG_SYNONYMS[:200]`
  cap, dedup-vs-text, and `build_knowledge_objects` dropping AlternativeTherapy/FirstLineTherapy/
  AgeRestriction (no else branch).
- PR-008 execution deferred until rebuild finishes (CPU contention rule).

### Iteration 3c (2026-07-14) — Root Cause Program + CKY metric + Retrospectives adopted
- Owner directive: stop opening PR-001/008/009 ad hoc; run a **Root Cause Program**. Created
  `ROOT_CAUSE_REGISTER.md` (permanent, ranked by benefit÷effort; PR findings migrated to RC-001…011;
  TECH_DEBT_BACKLOG subsumed as raw evidence log).
- Adopted **Clinical Knowledge Yield (CKY)** as north-star metric: `CLINICAL_KNOWLEDGE_YIELD.md`
  (overall + per axis: antibiotics/dose/duration/frequency/alternatives/first_line/pediatric/
  pregnancy/renal/contraindications/evidence). Wired CKY into `semantic_yield_audit.py` output.
- Started `ENGINEERING_RETROSPECTIVE.md`; wrote the RC-001 retrospective (why it shipped, why tests
  missed it, missing invariants, guards added, class-level prevention).
- PR-008 tool now emits: funnel + ranked loss histogram + CKY (overall & per dimension). Ready to
  run post-rebuild. Rebuild at 13 PDFs, KB 4490.

### Iteration 3b (2026-07-14) — PR-008 upgraded to per-candidate loss classification
- Owner requirement: classify EVERY table-derived candidate into exactly one loss/accept reason;
  emit a ranked histogram as a permanent benchmark ("know WHY every piece is lost", not just how much).
- Rewrote `semantic_yield_audit.py`: first-loss-wins classifier mirroring real production decision
  points (dedup vs text; KB-builder type gap; content-key duplicate; `_validate_basic`; confidence
  gate = none in prod → reported as 0). Emits funnel + ranked loss histogram (count + %) + reason
  breakdown per entity type. Output JSON is the benchmark artifact.
- Rebuild status: 11 PDFs, KB 3371 objects, 13 table-provenance rows (PR-001 holding at scale).
- Deferred execution until rebuild completes.

### Iteration 4 (2026-07-14) — P4.4 Final Completion Program launched (14 phases)
- Owner issued the strict P4.4 closure program. Phase 1 (let rebuild finish) in progress —
  **not interrupted** (72/192, KB 16065).
- Built the invariant + coverage layers (Phase 6 tooling) and CKY source axis (Phase 4) ahead of
  measurement. `PRODUCTION_SCORECARD.md` scaffold created (Phase 10).
- **Phase 8 (RC-012) done early (read-only, non-contending):** audited the full semantic→KB key
  mapping. RC-012 confirmed (raw vs text). **Not isolated** — found RC-013 (guideline_id +
  paragraph never populated) in the *same* provenance contract. Recommend a single joint
  provenance-contract fix + one KB re-run. Registered both.
- **Current determination (measured): P4.4 STAYS OPEN** — INV-09 is a blocking FAIL on real data
  (RC-012), independent of pending metrics.
- Deferred until rebuild completes: Phases 2-5 (counts/CKY/coverage), 9 (consistency), regression,
  perf. Tools ready and compile clean.

*(Next iterations appended here.)*
