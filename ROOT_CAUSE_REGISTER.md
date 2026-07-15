# ANTIBIO — Root Cause Register (RCR)
## Permanent engineering artifact · created 2026-07-14

> **Purpose (Root Cause Program):** Every issue discovered anywhere in ANTIBIO becomes a permanent
> entry here — it is NOT fixed on discovery. First it is *classified* (category, severity, impact,
> resolution type), then the whole register is *ranked by expected benefit ÷ effort*, and work
> proceeds highest-value-first. No issue disappears. This replaces ad-hoc PR-001…PR-0NN handling.
>
> **Prime directive:** The objective is not to fix bugs. It is to **maximize Clinical Knowledge
> Yield (CKY)** while preserving traceability, determinism, and reproducibility. Never optimize a
> local stage at the expense of global pipeline quality. CKY is defined in
> `CLINICAL_KNOWLEDGE_YIELD.md`.
>
> **Governed by** `docs/governance/`. Frozen scope (Clinical Engine, medical content, bundle
> schemas) changes only via RFC.

## Entry schema
Each entry records: **Category** (Architecture / Extraction / Layout / Semantic / Knowledge Model /
Normalization / Validation / Persistence / Documentation / Benchmark / Tooling) · **Severity**
(Critical / High / Medium / Low) · **Impact** (Clinical / Developer / Performance / Maintenance,
each Hi/Med/Lo/–) · **Resolution** (Bug Fix / Refactoring / Migration / Architecture Change / RFC) ·
**Benefit** & **Effort** (→ priority = Benefit ÷ Effort) · **Status** (Open / In Progress / Fixed /
Deferred / Tracked).

---

## Ranked backlog (by expected benefit ÷ effort — solve top first)

| Rank | ID | Title | Category | Sev | Clinical / Dev / Perf / Maint | Resolution | Benefit | Effort | Status |
|-----:|----|-------|----------|-----|-------------------------------|------------|:-------:|:------:|--------|
| — | RC-001 | Structured tables never reached KB (`tbbox` NameError, swallowed) | Layout | Critical | Hi / Hi / Hi / Med | Bug Fix | Very High | Low | **FIXED 2026-07-14** |
| 1 | RC-023 | **kb_p44 atomic objects have no intra-regimen linkage** — `relationships` empty on 100% of objects; drug↔dose↔route↔frequency associations never captured; objects cluster only by (guideline_id, page). Blocks deterministic atomic→regimen assembly (2 drugs × 52 unlinked doses/page = combinatorial guess). Discovered P5.3 Phase 0 (`P5.3_IMPLEMENTATION_AUDIT.md`). | Extraction / Knowledge Model | High | Hi / Hi / – / Hi | Architecture Change (extraction-layer linkage) | High | High | **Open** — v1 works around it via regimen-grained source (P5.1 MIGRATION_PLAN §2); atomic assembly deferred until fixed. |
| — | RC-024 | Regimen-modeling scope gap (42% REJECT). **RESOLVED architecturally 2026-07-15 (P5.5):** new `TherapeuticOption` type introduced, distinct from `ClinicalRegimen`. 652/1132 REJECTs (categories A+B, 57.6%) reclassified as class-level knowledge, migrated with 100% provenance (0 blocked). Remaining 467 REJECTs (categories C+D, 41.4% of original) are genuine unresolved issues (444 extraction gaps, 23 TB-noise → RC-026). | Knowledge Model / Architecture | High | Hi/Med/–/Med | Architecture Change | High | Med | **FIXED (architecture) 2026-07-15** — `THERAPEUTIC_OPTION_RULES.md`, `P5.5_IMPLEMENTATION_REPORT.md`. 33/33 tests pass. Physician-review population of both types remains open (not a code task). |
| 3 | RC-025 | `normalized_regimens` rows with `source_quote` misaligned to `drug_original` (2 confirmed in ~35-sample spot-check during P5.5; population-wide count not measured) | Extraction / Data Quality | Medium | Med/Lo/–/Med | Bug Fix (upstream extraction) | Med | Med | Open — discovered P5.5 manual verification (`RC024_CLASS_LEVEL_ANALYSIS.md`). `normalized_regimens.sqlite` frozen for this program; not fixed here. |
| 4 | RC-026 | Tuberculosis combination-regimen tables extract as bare abbreviation-code fragments (e.g. "H R/Rb Z E [S]") instead of structured regimens — 100% of P5.5's "D_invalid_noise" category (23 confirmed REJECTs) are TB-specific | Extraction / Layout | Medium | Med/Lo/–/Med | Bug Fix (TB-table-specific extraction) | Med | Med | Open — discovered P5.5 (`RC024_CLASS_LEVEL_ANALYSIS.md`). Not a `ClinicalRegimen` or `TherapeuticOption` candidate in current form. |
| — | RC-027 | `ReviewService.packet()` returned `original_source_wording: [None,...]` for ClinicalRegimen/TherapeuticOption/GoldenCase (2,215 tasks) — root cause: reads `item.get("original_text"/"source_quote")` off provenance dicts that never carry those keys (`FieldProvenance` has no such field; golden-case provenance uses `source`). **FIXED in the canonical path 2026-07-15**: `resolve_source_wording()` (`service.py`) implements the documented precedence (`REVIEW_PACKET_CONTRACT.md`) — field-level `original_text` → field-level `source_quote` → target-level `source_quote` → golden-case `source` → fail-closed `MISSING`/`review_blocked=true`. Verified on full population: ClinicalRegimen 1556/1556, TherapeuticOption 652/652, GoldenCase 7/7 now 100% populated; `ConflictRecord`(5615)/`CorpusExclusionDecision`(58) correctly and honestly report `MISSING` (out of scope, no provenance concept ever built for them — separate gap). | Review Workbench / Knowledge Model | High | Hi/Med/–/Med | Bug Fix | High | Low | **FIXED 2026-07-15** — `RC027_ROOT_CAUSE_REPORT.md`, `REVIEW_PACKET_CONTRACT.md`. 14/14 new regression tests + 93/93 existing suite pass. Pilot exporter's temporary substitution removed (uses canonical `service.py` path exclusively). |
| 3 | RC-028 | `TherapeuticOption` queue-builder ingestion hardcodes `safety_axes=[]`/`reasons=["missing_metadata"]` for all 652 tasks — no `_option_axes()` equivalent to `ClinicalRegimen`'s working `_regimen_axes()` was ever written, despite the object having the same free-text fields (`indication`/`therapeutic_class`/`source_quote`) that `_regimen_axes()` already scans successfully. Confirmed root cause (queue builder ignores available fields), not a model or migration defect. | Review Workbench | Medium | –/Med/–/Med | Bug Fix | Med | Low | Open — discovered 2026-07-15 (`THERAPEUTIC_OPTION_REVIEW_TAGGING_AUDIT.md`). Not fixed here (not part of RC-027); `PHYSICIAN_PILOT_V1`'s keyword fallback compensates for pilot selection only. |
| 1 | RC-008 | Table facts under-yield (quantify via PR-008 loss histogram) | Semantic | High | Hi / Med / – / Med | Bug Fix + Refactoring | High | Low-Med | Open (measuring) |
| — | RC-012+013+014+015 | **Provenance contract remediation** (one unified migration): original_text (raw≠text), guideline_id, engine label + table_conf, dead `semantic` column. Spec: `PROVENANCE_SPECIFICATION.md`. | Knowledge Model / Persistence | High | Hi / Med / – / High | Bug Fix + Migration | High | Low-Med | **FIXED & VERIFIED AT FULL SCALE 2026-07-15.** 192/192 PDFs, 100854 provenance rows: INV-09 = 0 violations (was 1442), 0 NULL original_text/guideline_id/extractor/layout_engine/semantic_engine/schema_version, 192/192 distinct guideline_id mapped, INV-17 (table_row⇒table_conf) 0 violations. |
| — | RC-017 | `_merge_provenance` collapsed distinct table cells (data loss) | Knowledge Model / Persistence | High | Hi/Hi/–/Med | Bug Fix | High | Low | **FIXED & VERIFIED 2026-07-15** — regression test in the 72-passed full suite; full-KB sweep found 0 same-page/multi-cell collapses. |
| — | RC-018 | v1 rows not backfilled to schema_version=1 | Persistence/Docs | Low | Lo/Lo/–/Lo | Bug Fix | Low | Very Low | **FIXED & VERIFIED 2026-07-15.** |
| — | RC-016 | RapidTable fallback broken by API drift | Extraction/Layout | Medium | Med/Med/Lo/Lo | Bug Fix | Med | Low | **FIXED & VERIFIED 2026-07-15** — full rebuild shows the fallback firing live (15 provenance rows via `layout_engine='rapidtable'`). |
| 1 | RC-019 | **Two disconnected knowledge stores** — Clinical Decision Engine reads `medical_normalizer.db`/`normalized_regimens.sqlite`, NOT `kb_p44.db`. P4.4's provenance/traceability guarantees do not reach served recommendations. | Architecture | **Critical** | Hi/Hi/–/Hi | Architecture Change + RFC | Very High | High | **Open** — found by Enterprise Architecture Review 2026-07-15 (`ENTERPRISE_ARCHITECTURE_REVIEW.md` EAR-1). Scope for P5. |
| 2 | RC-020 | Drug identity triplicated (code `DRUG_SYNONYMS`, `medical_normalizer` DB, `kb_p44` Medication objects) — drift risk | Knowledge Model | High | Med/Med/–/Hi | Architecture Change | High | Med | Open (EAR-2). Motivates a Clinical Knowledge Ontology (owner-proposed). |
| 3 | RC-021 | Engine's `diagnosis_index.json` is `AUTO_GENERATED_DRAFT/PARTIALLY_CURATED` — routing risk (wrong guideline silently selected) | Semantic / Clinical Governance | High | Hi/Lo/–/Med | Bug Fix + physician curation | High | Med | Open (EAR-3). |
| 4 | RC-022 | Status vocabulary drift: code writes `active`; canonical lifecycle is `draft→validated→published→superseded→deprecated` (Constitution). 28368 `active` + 2968 `superseded` objects in the fresh KB already carry the non-canonical value. | Knowledge Model | Medium | –/Med/–/Hi | Migration | Med | Med | Open (EAR-8, RFC P5-KP-001 §2.2 Q1). Grows more expensive the longer it ships. |
| 3 | RC-009 | `build_knowledge_objects` drops AlternativeTherapy/FirstLineTherapy/AgeRestriction (no else) | Knowledge Model | High | Hi / Lo / – / Med | Bug Fix | High | Low | Open (hypothesis, PR-008 to confirm) |
| 3 | RC-010 | `DRUG_SYNONYMS[:200]` cap in table drug scan | Semantic | Medium | Med / – / Lo / Lo | Bug Fix | Med | Low | Open |
| 4 | RC-002 | KnowledgeObject schema drift, no migration tool (204 NULL knowledge_type) | Persistence | High | – / Med / – / Hi | Migration | Med | Med | Open |
| 5 | RC-007 | No CI pipeline (no automated test/regression gate) | Tooling | Medium | – / Hi / – / Hi | Architecture Change | Med | Med | Open |
| 6 | RC-004 | Repo-root clutter (24 probe scripts, 19 logs, 12 json, 3 DBs) | Tooling | Medium | – / Med / – / Med | Refactoring | Med | Low-Med | Open |
| 7 | RC-005 | No automated milestone doc-consistency gate | Documentation | Medium | – / Med / – / Med | Tooling | Med | Low | Open |
| 8 | RC-006 | Overlapping knowledge DBs at root, unclear authority | Persistence | Low | – / Med / – / Med | Refactoring | Low | Low | Open |
| 9 | RC-011 | `_get_by_key` uses `content LIKE %..%` (substring) for dedup — false-positive/negative risk | Knowledge Model | Medium | Med / Lo / Med / Med | Refactoring | Med | Med | Open (spotted during PR-008 code read; confirm) |
| — | GOV-001 | `ReviewService` accepted arbitrary reviewer strings — no dependency on a reviewer identity/registration system, so any caller could claim/submit/adjudicate under a fabricated identity. | Review Workbench / Governance | High | Hi/Med/–/Hi | Architecture Change | High | Med | **FIXED 2026-07-15** — `reviewer_registry.py` (`ReviewerRegistry.validate_reviewer_action`) wired into every `ReviewService` write path; rejected attempts audit-logged without state change. `P56_REVIEW_GOVERNANCE_HARDENING_REPORT.md`. |
| — | GOV-002 | `ReviewService.packet()` leaked Reviewer A's decision/rationale/reason codes to Reviewer B unconditionally once a task reached `SECOND_REVIEW`, via the packet, audit history, and the unauthenticated `GET /tasks/{id}` API — broke reviewer independence. | Review Workbench / Governance | High | Hi/Med/–/Hi | Bug Fix + API change | High | Med | **FIXED 2026-07-15** — `packet_for_reviewer()` role/state-aware redaction; `GET /tasks/{id}` now requires `reviewer_id`+`role`. `SECOND_REVIEW_BLINDING_SPEC.md`. |
| — | GOV-003 | `governance_state(ACCEPTED)` reported `PHYSICIAN_APPROVED` the instant two reviewers agreed, with no Medical QA Lead sign-off gate — the most severe of the three, since it meant the system's own governance status could read "approved" without any QA review ever happening. | Review Workbench / Governance | **Critical** | Hi/Hi/–/Hi | Architecture Change | Very High | Med | **FIXED 2026-07-15** — new `MEDICAL_QA_PENDING` state + mandatory `submit_medical_qa_signoff()` gate; `PHYSICIAN_APPROVED`/`REJECTED` only reachable through it. `REVIEW_CONSENSUS_STATE_MODEL.md`, `MEDICAL_QA_SIGNOFF_SPEC.md`. |
| — | RC-029 | `BasicTerminologyProvider.__init__` (`clinical_engine/terminology.py`) mutated the `functools.lru_cache`-cached dict returned by `medical_dictionary.loader.load_drug_atc()` in place via `.setdefault("unmapped_pen", ...)`, permanently corrupting the process-wide cached singleton the first time any code constructed the provider. Caused `medical_normalizer/tests/test_medical_dictionary_loader.py::TestLoaderDrugAtc::test_empty_until_review` to fail whenever `clinical_engine/tests/test_engine.py` or `test_golden_runner.py` ran first in the same process — order-dependent, but with a fully deterministic, reproduced-outside-pytest root cause (`MEDICAL_DICTIONARY_TEST_ISOLATION_RCA.md`), not flakiness. Does not affect the canonical `python -m pytest` command, whose `testpaths` order runs `medical_normalizer/tests` first. | Clinical Engine / Test Isolation | Medium | Lo/Med/–/Med | Bug Fix | Med | Low | **FIXED 2026-07-15** — `self._atc_map = dict(load_drug_atc())` (defensive copy before mutating). Regression test: `clinical_engine/tests/test_terminology_cache_isolation.py`. |

*(Ranking is provisional until PR-008 numbers land; benefit for RC-008/009/010 will be re-scored
from the measured loss histogram + CKY deltas.)*

---

## Entry details

### RC-001 — Structured tables never reached the Knowledge Base — FIXED
- **Category:** Layout · **Severity:** Critical · **Resolution:** Bug Fix.
- **Root cause:** `layout.py::_extract_table_with_transformers` referenced `tbbox` before
  assignment → `NameError` per table → swallowed by bare `except: pass` → 0 structured tables.
- **Impact:** Clinical Hi (all table-origin dosing/alt/peds lost), Dev Hi (hours of layout CPU for
  zero yield), Perf Hi, Maint Med.
- **Fix + validation + regression:** see `AI_LOG.md` 2026-07-14 and `PRODUCTION_READINESS_PROGRAM.md`
  PR-001. Verified structured_tables 0→29, KB table_row 0→4. Tests added.
- **Retrospective:** `ENGINEERING_RETROSPECTIVE.md#rc-001`.

### RC-008 — Table-derived clinical facts under-yield (quantification in progress)
- **Category:** Semantic · **Severity:** High · **Resolution:** Bug Fix + Refactoring.
- **Symptom:** 29 tables → 4 KB objects on Сепсис. **Being measured** by PR-008 loss-classification
  histogram + CKY. Do not fix until the ranked loss reasons are known.

### RC-009 — KB builder silently drops high-value table entity types — CONFIRMED by CKY 2026-07-15
- **Category:** Knowledge Model · **Severity:** High · **Resolution:** Bug Fix.
- **Root cause:** `build_knowledge_objects` if/elif has no else; AlternativeTherapy / FirstLineTherapy
  / AgeRestriction produced by the table path are dropped.
- **Confirmed by measurement:** full CKY baseline (`pr008_yield_FINAL.json`) shows
  `CKY.tables = 1.1%` (1/95 table candidates accepted) and `CKY.alternatives = 0.0%` /
  `CKY.pediatric = 0.0%` — the hypothesis is now measured fact, not conjecture. Also explains the
  `Coverage.duration/frequency/pediatric = 0%` finding. Highest-ranked open item post-certification.

### RC-010 — Table drug scan capped at first 200 synonyms
- **Category:** Semantic · **Severity:** Medium · **Resolution:** Bug Fix.
- `extract_entities_from_tables` iterates `list(DRUG_SYNONYMS.items())[:200]` — drugs beyond the
  first 200 synonyms are invisible in table cells. Confirm cost via PR-008.

### RC-012 — Original drug wording not preserved in provenance — CONFIRMED
- **Category:** Knowledge Model · **Severity:** High · **Resolution:** Bug Fix (one line).
- **Discovered by:** the INV-09 architectural-invariant check (1442 `Medication` violations),
  verified against raw KB rows (`original_text=None` while `normalized_value='амоксициллин'`).
- **Root cause:** `knowledge_base.py:244` sets `original_text=src.get("original_text") or
  item.get("text")`, but `build_knowledge_objects` stores the raw wording under key **`"raw"`**,
  not `"text"` → `item.get("text")` is None → provenance loses the original wording.
- **Impact:** Clinical Governance violation ("never discard original wording"); breaks
  traceability from normalized drug back to source phrasing. **Blocks P4.4 closure** (INV-09 is a
  blocking invariant).
- **Fix (queued, not yet applied — Root Cause Program):** read `item.get("raw")` as well. Requires
  KB re-run to backfill (fold into the post-rebuild decision, do not thrash the in-flight rebuild).

### RC-013 — Provenance guideline_id + paragraph never populated (same contract as RC-012)
- **Category:** Knowledge Model · **Severity:** Medium · **Resolution:** Bug Fix + small feature.
- **Discovered by:** Phase 8 repo-wide key-mapping audit (RC-012 follow-through — "do not assume
  isolated"). The semantic entity provenance dict (`_mk_ent` / `extract_entities_from_tables`) sets
  `{page, engine, source, row, col, bbox, ...}` but never `guideline_id` or `paragraph`;
  `knowledge_base.add_document` reads `src.get("guideline_id")` / `src.get("paragraph")` → always
  null. Confirmed: provenance sample had `guideline_id=None, paragraph=None`.
- **Impact:** Clinical Governance traceability gap (no paragraph-level "where did it come from").
  Not object-dropping, so Medium.
- **Joint fix (with RC-012):** RC-012 and RC-013 are the **same semantic→KB provenance-mapping
  contract**. Fix together as one change: (a) read `item.get("raw")` for original_text; (b) thread
  `guideline_id` (from `doc.metadata`) + `paragraph` into the entity provenance. One KB re-run
  backfills both. Do not ship two incompatible partial fixes.

### RC-014 — Provenance engine mislabeled; producer `engine`/`table_conf` dropped
- **Category:** Knowledge Model · **Severity:** Medium · **Resolution:** Bug Fix (part of unified
  provenance-contract migration).
- **Found by:** Provenance Contract Audit (`PROVENANCE_CONTRACT_MATRIX.md`). `add_document` infers
  `layout_engine`/`semantic_engine` from a string match on `source` instead of reading the entity's
  actual `engine` key (which it ignores); mislabels table cells as `doclayout-yolo` when the real
  engine is `table-transformer+rapidtable`. The `table_conf` quality signal is dropped entirely.
- **Impact:** provenance engine attribution is inaccurate (traceability quality), lost confidence
  signal. Fix within the single migration (RC-012/013/014/015).

### RC-015 — Dead legacy `semantic` column in provenance schema
- **Category:** Persistence · **Severity:** Low · **Resolution:** Migration.
- **Found by:** Provenance Contract Audit. Base `CREATE TABLE provenance` declares `semantic`, but
  the INSERT writes `semantic_engine` (migrated col); `semantic` is never populated → dead column.
- **Fix:** retire in the same schema migration; version the provenance schema.

### RC-017 — `_merge_provenance` collapses distinct table cells (silent data loss) — FIXED 2026-07-14
- **Category:** Knowledge Model / Persistence · **Severity:** High · **Resolution:** Bug Fix.
- **Found by:** Independent Auditor pass (adversarial "try to disprove the migration"). Proven with
  a synthetic probe: same object in cells (row1,col2) and (row9,col4) on the same page → only the
  first survived. Dedup key was `(pdf, page)`, dropping cell-level provenance — a direct violation
  of INV-03 / Clinical Traceability at cell granularity.
- **Fix:** dedup key → `(pdf, page, table_row, table_col)`; true duplicates still deduped, distinct
  cells retained. Regression test `test_merge_provenance_retains_distinct_cells`. Re-probe: both
  cells kept, true dup ignored.
- **Note:** this defect was in the provenance layer I had *just declared fixed* — the auditor
  mindset (prove it wrong, not right) is exactly what surfaced it.

### RC-018 — v1 provenance rows not backfilled to schema_version=1 — FIXED 2026-07-14
- **Category:** Persistence / Documentation · **Severity:** Low · **Resolution:** Bug Fix.
- **Found by:** Independent Auditor (backward-compat probe on a real v1 DB). Spec promised backfill
  to 1; migration left NULL (48617 rows). Doc-doesn't-match-implementation.
- **Fix:** idempotent `UPDATE provenance SET schema_version=1 WHERE schema_version IS NULL` in the
  migration. Re-probe: v1 rows now report schema_version=1.

### RC-016 — RapidTable fallback broken by API drift — FIXED 2026-07-14
- **Category:** Extraction/Layout · **Severity:** Medium · **Resolution:** Bug Fix.
- **Found by:** the PR-001 observability logging (converted bare `except: pass` → `logger.warning`)
  surfaced `RapidTable fallback failed: cannot unpack non-iterable RapidTableOutput object` on ~40
  pages during the provenance-v2 verification run. rapid-table ≥3 returns a `RapidTableOutput`
  (`.pred_htmls` list), not a `(html, elapse)` tuple.
- **Impact:** the RapidTable fallback table path was dead (silently, before observability) → pages
  where Table Transformer found nothing got no fallback. Primary path unaffected.
- **Fix:** `_rapidtable_html()` adapter in `layout.py` handles both new object + legacy tuple; both
  call sites updated. Compiles; tests green. Fixed before the definitive rebuild so the fallback is
  functional in it (avoids a third rebuild). *Meta-lesson: this is the second silent failure the
  RC-001 observability change has caught — validates INV-14 (no silent failure).*

### RC-011 — Content-key dedup via SQL `LIKE %substring%`
- **Category:** Knowledge Model · **Severity:** Medium · **Resolution:** Refactoring.
- `_get_by_key` matches `content LIKE '%<key-suffix>%'` — a substring scan over serialized JSON.
  Risk: false merges (one drug name substring of another) and false misses. Needs a real key column
  + index. Confirm with data before acting.

*(RC-002/004/005/006/007 detail mirrors `TECH_DEBT_BACKLOG.md` TD-002/004/007/005/006 respectively;
that backlog is now subsumed under this register — TECH_DEBT_BACKLOG.md remains as the raw evidence
log, RCR is the ranked decision surface.)*

---

## Process
1. New issue → add entry here first (classify), do **not** fix immediately.
2. Score Benefit ÷ Effort; re-rank the backlog.
3. Work top-ranked. For Architecture Change / RFC resolutions → open an RFC (`RFC_INDEX.md`) first.
4. On fix: update entry Status, link the retrospective, add regression protection.
5. Never let a discovered issue vanish. Deferred ≠ deleted (record the justification).
