# ENTERPRISE_ARCHITECTURE_REVIEW.md
## ANTIBIO — whole-system architecture review · 2026-07-15 · read-only (code freeze respected)

> Not another RFC. A cross-cutting review of architecture + code + pipeline + governance to answer
> three questions: (1) undiscovered architectural risks, (2) what becomes the bottleneck within a
> year, (3) decisions that look right now but will likely force expensive refactoring in 2–3
> milestones. Findings are grounded in the actual code (paths cited), not the design docs.
> New risks are **registered** in the Root Cause Register, not fixed (freeze).

---

## Q1 — Architectural risks NOT yet discovered

### EAR-1 (CRITICAL) — Two disconnected "knowledge bases"; the engine does not read the Production KB
**Evidence (verified):**
- The P4.4 pipeline (`src/pipeline/`, `build_p44_kb.py`) builds `kb_p44.db` — versioned
  KnowledgeObjects + the provenance layer this whole session hardened (RC-012…018, CKY, coverage,
  certification).
- The Clinical Decision Engine (`clinical_engine/`) reads a **different** source:
  `clinical_engine/readers/sqlite_reader.py` wraps `medical_normalizer.db` / `NormalizerDB` +
  `normalized_regimens.sqlite` + `metadata.sqlite` from `C:\clinrec_downloader`
  (`corpus/corpus_config.json`), plus a `diagnosis_index.json` resource.
- Grep confirms: `clinical_engine/` has **zero** references to `kb_p44` / `KnowledgeBase`; the P4.4
  pipeline does **not** write `normalized_regimens.sqlite`.

**Why it matters:** certifying P4.4 as "production ready" does **not** make the engine consume it.
All provenance/CKY/traceability guarantees live in `kb_p44.db`, but clinical recommendations are
served from the separate normalized-regimens store. The end-to-end promise — "every recommendation
traces to guideline page/table/original wording" — is **not currently wired**, because the layer
that has that provenance (P4.4) and the layer that answers clinically (engine) are not connected.
This is the single most important finding: the two halves of the platform were built in parallel
against different stores. → registered as **RC-019**. The bridge (KB → engine regimen source, or
re-point the engine at `kb_p44.db`) is unbuilt and belongs in P5/P6 as a first-class deliverable,
not an afterthought.

### EAR-2 (High) — Source-of-truth for drug identity is triplicated
Drug identity exists in at least three places: `DRUG_SYNONYMS` in `src/pipeline` code, the
`medical_normalizer` DB the engine reads, and the `Medication` objects in `kb_p44.db`. There is no
single canonical drug ontology; the three can drift. (This is exactly why the owner's proposed
Clinical Knowledge Ontology is high-value — it would collapse these into one.) → **RC-020**.

### EAR-3 (Medium) — The engine's diagnosis routing depends on a DRAFT resource
`clinical_engine/config.py` notes `diagnosis_index status is AUTO_GENERATED_DRAFT /
PARTIALLY_CURATED`. Clinical routing (which guideline applies) rides on a not-fully-curated index.
A wrong route silently selects the wrong guideline. Needs the same physician-verification rigor as
the Golden Dataset. → **RC-021**.

### EAR-4 (Medium) — Provenance guarantees are enforced only at the KB boundary, not end-to-end
INV-01…17 validate `kb_p44.db`. Nothing validates that a *served recommendation* carries provenance
back to a guideline. Given EAR-1, the invariant suite can be all-green while the user-facing answer
has no lineage. Invariants must eventually span the serving path (P5 Explainability API).

---

## Q2 — What becomes the bottleneck within ~1 year

### EAR-5 (High) — SQLite + substring scans will not carry query/search load
- `knowledge_base.py::_get_by_key` matches `content LIKE '%<suffix>%'` over serialized JSON
  (already logged as RC-011). This is an O(n) table scan per lookup with false-merge/false-miss
  risk. Fine at ~20k objects offline; it will not survive the P5 Query/Search/Diff APIs under
  concurrent load.
- The whole store is file-based SQLite with hardcoded local paths (`C:\clinrec_downloader`). P7
  (Production Ecosystem / service deployment) cannot ship this as-is: no connection model, no
  concurrency story, no network boundary. **The bottleneck is not compute — it's that the storage/
  access layer was designed for a single-machine batch pipeline, and P5+ assume a queryable service.**
- Rebuild throughput itself (some PDFs 400–485 s, whole corpus multi-hour, single process) becomes a
  CI bottleneck the moment continuous validation (RC-007 CI) runs the full corpus. QA Program's
  "nightly full-corpus" gate needs an incremental/cached rebuild or it won't fit.

### EAR-6 (Medium) — Physician review is the real throughput limit, and there is no tooling for it
Golden Dataset (500+), Clinical Validation (double-review + adjudication), diagnosis-index curation
all depend on physician hours. There is no review workbench/queue UI yet (P5 Review Workflow is
still an RFC). Within a year, the constraint on clinical coverage is human review capacity, not
engineering — and the tooling to make that capacity efficient is unbuilt.

---

## Q3 — Decisions that look right now but will likely need expensive refactoring in 2–3 milestones

### EAR-7 — Parallel-store design (the EAR-1 split) will force a painful reconciliation
Continuing to evolve `kb_p44.db` and `normalized_regimens.sqlite` independently means P6 will need a
migration/bridge that reconciles two schemas, two id spaces, and two provenance models retroactively
— far more expensive than picking one canonical store now. Cheapest window to decide is P5.

### EAR-8 — Status-vocabulary drift (`active` vs canonical lifecycle) baked into every object
Code writes status `active`; the Constitution's lifecycle is
`draft→validated→published→superseded→deprecated`. Every object in every rebuilt KB carries the
non-canonical value. The longer this ships, the larger the eventual data migration (already noted by
the P5 RFC). → **RC-022**. Decide the canonical state machine before P5 serves objects by status.

### EAR-9 — Provenance/knowledge schema evolved by additive `_migrate_add_column` only
The KB schema grows by adding nullable columns (14+ on `provenance`, dead `semantic` column left in
place per RC-015). This is fine for a few cycles but there is no schema-version table, no down-
migration, no rebuild-from-scratch contract. By P7 the additive-only strategy yields a wide, partly-
dead schema that's hard to reason about. A real migration framework (versioned, reversible) is the
eventual expensive fix; introducing it early is cheap.

### EAR-10 — Engine reads a FROZEN normalizer DB; "frozen" will collide with guideline updates
`sqlite_reader.py` wraps the **frozen** `medical_normalizer.db`. P9 (multi-guideline) and routine
MoH guideline updates require the served knowledge to change. A frozen upstream that the engine
binds to directly means every guideline refresh is a frozen-artifact rebuild + re-freeze, not a
data update. The freeze that gives determinism today becomes an update bottleneck later; the fix
(versioned, swappable knowledge snapshots the engine pins to) is an architecture change best scoped
in P5.

---

## Synthesis — the one thing to decide before P5
Almost every Q3 item traces to **EAR-1**: two knowledge stores built in parallel. The highest-
leverage architectural decision is to pick a single canonical, versioned, queryable knowledge store
that BOTH the provenance layer and the Clinical Decision Engine use, and design P5 around it. Doing
this in P5 is a design choice; discovering it in P6/P7 is an expensive migration. Everything else
(ontology, normalization library, explainability, monitoring) is more valuable once there is one
store to hang it on.

*New risks registered:* RC-019 (two-KB split, Critical), RC-020 (triplicated drug identity),
RC-021 (draft diagnosis index), RC-022 (status vocab drift). Registered only — not fixed (freeze).
Ranking to be scored into the Root Cause Register during post-rebuild consolidation.
