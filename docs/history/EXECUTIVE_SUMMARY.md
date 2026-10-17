# EXECUTIVE_SUMMARY.md
## RC-019 — Dual Knowledge Stores → Single Source of Truth · P5.0 Migration Program
## 2026-07-15 · Architecture & Migration program (no code, no implementation)

> Entry point for the P5.0 package. Read this first; it indexes the other seven documents and
> answers the ten Phase-10 questions directly. Every claim below is grounded in the real repository
> (paths cited); anything not provable from the repository is marked **UNKNOWN**.

## Document package
| Document | Phase(s) | Content |
|---|---|---|
| `EXECUTIVE_SUMMARY.md` (this file) | 1, 2, 9, 10 | Current state, verdict, exit criteria |
| `P5_MIGRATION_MASTER_PLAN.md` | 1–10 | Full narrative: architecture, flows, phased plan |
| `SINGLE_SOURCE_OF_TRUTH_RFC.md` | 3 | Which store is canonical, and why |
| `KNOWLEDGE_PLATFORM_MIGRATION_RFC.md` | 4 | 5-phase migration, rollback, validation, cutover |
| `CLINICAL_ENGINE_ADAPTER_RFC.md` | 5 | How the engine consumes the SSOT without behavior change |
| `QUERY_LAYER_RFC.md` | 5 (detail) | Repository/ports/caching/indexing/read-only guarantees |
| `DECISION_MATRIX.md` | 8 | Option A/B/C/D compared |
| `RISK_REGISTER.md` | 6 | Every risk found, ranked |

Ten named sub-RFCs from the mandate's Phase 7 (SSOT, Migration Strategy, Query Layer, Compatibility
Layer, Clinical Engine Adapter, Knowledge Repository, Repository Interfaces, Caching, Versioning,
Rollback) are **not** ten separate files — the Deliverables list names 8 files, which is authoritative.
Each topic is a section inside one of the 8: Compatibility Layer + Rollback + Versioning →
`KNOWLEDGE_PLATFORM_MIGRATION_RFC.md`; Knowledge Repository + Repository Interfaces + Caching →
`QUERY_LAYER_RFC.md`. Nothing from Phase 7 is dropped; it is consolidated, not omitted.

---

## Phase 1 — Current state (grounded, not assumed)

**There are not two independent pipelines feeding two stores. There are three extraction
pipelines, converging into two storage endpoints, currently unreconciled:**

1. **LLM regimen pipeline (original, pre-P4.4)** — `main.py` / `src/pipeline/main.py` CLI
   (`download → analyze → filter → classify → gate → extract_raw → validate → knowledge → update
   → verify`). `src/pipeline/extractor_llm.py` runs a two-pass LLM extract+validate over guideline
   text, producing **per-regimen** structured rows (antibiotic, dose, unit, frequency, route,
   duration, age_group, pregnancy, renal_adjustment, each with a field-level confidence) written by
   `save_regimens()` in `src/pipeline/database.py` to **`metadata.sqlite::antibiotic_regimens`**
   (2,675 rows, **100% `validated=1`**, real count verified read-only).
2. **Normalizer projection** — `clinical_engine/tools/build_normalized_sqlite.py` reads
   `antibiotic_regimens`, runs each row through the **FROZEN** `medical_normalizer` package
   (`MedicalNormalizer.normalize()`), and writes **`normalized_regimens.sqlite`** (2,675 rows,
   verified) via `medical_normalizer/db.py::NormalizerDB`. Schema: 41 columns including
   `review_status`, `reviewed_by`, `review_date`, `approved`, `schema_version` — a **mature,
   already-versioned, human-review-aware schema**, not a legacy stub.
3. **P4.4 rule-based pipeline (this session's subject)** — `build_p44_kb.py` →
   `src/pipeline/extraction/{router,layout,semantic}.py` (PyMuPDF + DocLayout-YOLO + Table
   Transformer + regex/dictionary entity extraction, **no LLM**) → generic `KnowledgeObject`s →
   `src/pipeline/knowledge_base.py::KnowledgeBase` → **`kb_p44.db`** (31,336 objects, certified
   2026-07-15, see `PRODUCTION_SCORECARD.md`).

**Who reads what today:**
- `clinical_engine/engine.py::Engine.__init__` opens `SQLiteReader(config.sqlite_path)`
  (`clinical_engine/readers/sqlite_reader.py`), which wraps `NormalizerDB` and reads
  `normalized_regimens` exclusively. **The engine has zero references to `kb_p44` or
  `KnowledgeBase`** (grep-verified, both directions).
- `clinical_engine/corpus/provenance.py` ("P3 INT-2") is a **separate, already-built,
  deterministic, read-only provenance resolver** chaining
  `regimen_id → normalized_regimens (guideline_id, review status) → metadata.antibiotic_regimens
  (pdf_file, sha256, page, quote) → metadata.clinrecs → the PDF on disk (SHA-256 verified)`.
  **This means the engine's current pipeline is NOT traceability-blind** — it has its own
  provenance chain, methodologically independent of (and not audited to the same rigor as) the
  `kb_p44` provenance contract this session certified.
- Nothing writes `kb_p44.db` from the LLM pipeline, and nothing reads `kb_p44.db` at all outside
  its own build/audit tooling (`src/pipeline/knowledge_*.py`).

**Corrected framing of RC-019:** not "the engine has no provenance," but **"two independently
engineered, unreconciled knowledge pipelines exist, at different granularities (bundled regimen vs.
atomic fact) and different extraction methods (LLM vs. rule-based), each with its own provenance
model, and only one of them is what the engine actually serves."** This is still a real, critical
architectural risk (duplicated investment, drift risk, unclear long-term ownership, P4.4's new
rigor orphaned from production serving) — it is a more precise, more actionable risk than "the KB
is disconnected."

## Phase 2 — Canonical data flow (see `P5_MIGRATION_MASTER_PLAN.md` §2 for full diagrams)
Current: three converging pipelines, two independent serving stores, engine bound to one.
Future: one canonical store, one write path per data class, engine bound to it via a stable port.
Transition: additive (build the new read path beside the old, prove parity, cut over, retire).

## Phase 9 — Exit criteria for RC-019 (summary; full table in the Migration RFC)
RC-019 is **CLOSED** only when ALL of:
- **Technical:** the engine's `SQLiteReader`-equivalent reads exclusively from the canonical store
  in production; `normalized_regimens.sqlite` is either retired or demoted to a read-only cache
  rebuilt FROM the canonical store (not an independent source).
- **Clinical:** golden-case parity — every case in `clinical_engine/golden_cases/` produces an
  identical `RecommendationSet` (same `regimen_id` ranking, same safety flags) pre- and post-cutover.
- **Performance:** p95 query latency for `Engine.recommend()` does not regress versus the current
  SQLite-file baseline (see `QUERY_LAYER_RFC.md` for the measurement plan — no numeric baseline
  exists in the repo today; this is marked UNKNOWN until measured).
- **Governance:** the frozen Clinical Decision Engine spec (`docs/superpowers/specs/
  clinical-decision-engine-v1.md`) is either satisfied unmodified, or a governed RFC amends it
  (frozen scope cannot be silently reinterpreted).
- **Documentation:** `ROOT_CAUSE_REGISTER.md` RC-019 entry updated to Fixed with evidence; ADR
  recording the SSOT decision.

## Phase 10 — Final verdict (direct answers)

**1. Should P5 start with migration?**
Yes, but as the **first deliverable within P5**, not a prerequisite blocking all other P5 work.
Query/Search/Versioning APIs (already RFC'd in `docs/rfc/P5_KNOWLEDGE_PLATFORM_RFC.md`) are more
valuable if built against the eventual canonical store from day one, rather than built against
`kb_p44.db` and then re-pointed later. Sequencing: SSOT decision + Migration Phase 1 (below) before
building new P5 surface area on top of either store.

**2. Should `kb_p44` become the Single Source of Truth?**
**Not directly, as-is.** `kb_p44.db`'s provenance/versioning/invariant rigor is exactly what a SSOT
needs, but its granularity (atomic Dose/Medication/Contraindication facts) is not what the engine
consumes (bundled `RecommendationCandidate` regimens) — see `RecommendationCandidate` in
`clinical_engine/models.py`, 24 fields, one row per regimen. The recommended design (full
justification in `SINGLE_SOURCE_OF_TRUTH_RFC.md`) is: **`kb_p44`'s schema and provenance contract
become canonical, extended with a `Regimen` aggregate object type that bundles the atomic facts —
not a wholesale swap to the existing atomic-only schema.**

**3. Should `medical_normalizer.db` survive?**
The **normalizer code** (the FROZEN `medical_normalizer` package: parsers, confidence, validator)
should survive — it encodes real clinical-text-normalization logic with no equivalent in the P4.4
pipeline. The **`normalized_regimens.sqlite` file as an independent source of truth** should not
survive past migration — it becomes a generated read-optimized projection, rebuilt from the
canonical store, or is retired if the query layer serves `RecommendationCandidate` shape directly.

**4. Can migration occur without breaking determinism?**
Yes, if done as specified in `KNOWLEDGE_PLATFORM_MIGRATION_RFC.md`: additive build of the new path,
byte-for-byte/field-for-field parity testing against the frozen engine spec's golden cases BEFORE
cutover, and a read-only, versioned canonical snapshot the engine pins to per request (never a live
mutable read during a recommendation). Same input + same pinned snapshot version ⇒ same output is
preserved by construction, not by care.

**5. What is the safest migration path?**
**Adapter-first, dual-read validation, then cutover** (Decision Matrix Option C, refined) — build a
`kb_p44`-backed reader implementing the exact `SQLiteReader`/`RegimenProviderAdapter` contract the
engine already depends on, run it in shadow (dual-read, compare, log divergence) against the golden
dataset and production traffic patterns, and only cut the engine over once divergence is zero on
the full golden set and explained/accepted on any residual production divergence. Never a big-bang
swap.

**6. Chief Architect's 5-year recommendation:**
Do not choose between the two pipelines by fiat. The LLM pipeline's regimen-level, human-reviewable
model is closer to what clinicians and the engine need *today*; the rule-based P4.4 pipeline's
provenance/invariant discipline is what the platform needs at *scale* and for *auditability*, and it
scales to corpora and guideline updates the LLM extract+validate loop cannot (cost, latency,
determinism). The 5-year-correct architecture converges them: **one canonical, versioned Knowledge
Object model (kb_p44's contract) that supports both atomic facts (for audit/traceability) and
regimen aggregates (for engine consumption), fed by whichever extraction method is more reliable
per field** (rule-based for tables the layout pipeline handles well; LLM-assisted for prose the
rule-based pipeline under-yields on — CKY.tables=1.1% measured this session). Do not delete the LLM
pipeline's clinical judgment; do not keep two unreconciled stores either. Converge the *model*, not
just the *storage*.

---

*Grounding note: all row counts, schema fields, and code paths in this document were verified by
direct repository/DB inspection on 2026-07-15, read-only, during code freeze. No production code,
tests, or databases were modified to produce this package.*
