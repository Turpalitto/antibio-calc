# Dataset Pruning Report for ANTIBIO Working Medical Base

**Date:** 2026-07-10
**Mode:** READ ONLY analysis (no changes to code, data, parser, normalizer, extraction, STTR, Medical Dictionary, SQLite schema)
**Context:** Post RCA. Parser/normalizer near architectural ceiling. Missing fields in raw = extraction problem only. Next leap via STTR.

**Source data used (read-only):**
- clinical_data_issues.json (4506 issues, 291 unique guideline_ids with antibiotic data)
- clinical_engine/resources/diagnosis_index.json (895 entries, 294 unique guideline_ids)
- Project docs: 294 guidelines with antibiotic regimens extracted, 2675 regimens total.
- Verdicts from antibio_data in issues for classification.

## Classification of Guidelines (LEVEL A/B/C)

**LEVEL A (Full antibiotic regimens - keep in working base):**
- Guidelines with at least one regimen having complete data (verdict PASS or full fields in antibio_data).
- Count: 58 guidelines
- Regimens: 1039 (the PASS regimens)

**LEVEL B (Mentions antibiotics but no full scheme - do NOT delete or modify; put in STTR queue):**
- Guidelines with regimens but only incomplete/problematic (REVIEW or REJECT, no PASS).
- Count: 233 guidelines (291 - 58)
- Regimens: 1636 (REVIEW 443 + REJECT 1193)

**LEVEL C (No antibiotics at all - candidates for exclusion from working base):**
- Guidelines in the current index but with no antibiotic regimens/data.
- Count: 3 guidelines (294 unique in diagnosis_index - 291 with data)
- Regimens: 0

**Note:** All numbers MEASURED from the JSON data (unique gids from issues and diagnosis_index, regimens from project docs and verdict counts). No estimation for counts.

## Performance Analysis - Current vs After Pruning LEVEL C (Simulation Only)

Pruning LEVEL C means removing the 3 guidelines with 0 regimens from the working base (index, RAG, embedding, search scope). Regimens and their data remain unchanged.

**1. Number of guidelines:**
- Current: 294 (MEASURED from diagnosis_index unique gids)
- After: 291
- Reduction: 3 (1.0%)

**2. Number of regimens:**
- Current: 2675 (MEASURED from project docs)
- After: 2675 (no change, LEVEL C contribute 0)
- Reduction: 0

**3. Number of RAG documents (assuming 1 per guideline):**
- Current: 294 (ESTIMATE based on unique gids)
- After: 291
- Reduction: 3 (1.0%)

**4. SQLite size (estimated proportion):**
- Current: regimens table dominant (2675 rows) + guideline table (294 rows) + related (MEASURED counts from docs)
- After: regimens same, guideline table 291 rows
- Reduction: ~1% on guideline-related portion (small overall; regimens unchanged). Exact size not in repo for full normalized SQLite (ESTIMATE based on row counts).

**5. Number of rows in key tables (MEASURED counts):**
- guideline: 294 → 291
- regimen: 2675 → 2675
- diagnosis: unchanged (linked to kept regimens)
- antibiotic, route, frequency, duration: unchanged (data from kept regimens)
- Other link tables: minimal change (only if exclusively linked to LEVEL C, which have 0 regimens)

**6. Number of records viewed by search:**
- Current: 2675 regimens + supporting guideline/diagnosis (MEASURED)
- After: same (2675 regimens)
- Reduction: 0 for core search (small for guideline metadata)

**7. Size of embedding (ESTIMATE):**
- Current: proportional to 294 guideline documents
- After: 291
- Reduction: ~1%

**8. Size of SQLite index (ESTIMATE):**
- Current: indexes on 294 guidelines + 2675 regimens
- After: indexes on 291 + 2675
- Reduction: ~1% on guideline portion

**9. Size of exported base (ESTIMATE):**
- Current: full with 294 guidelines
- After: with 291
- Reduction: ~1% (small, since regimens dominate)

**10. Benchmark search (no full SQLite in repo for direct; ESTIMATE based on row counts and previous perf audit):**
- Previous perf: recommend() ~8-17ms P95 on full 2675 (MEASURED in perf audit).
- After pruning C: no change to regimens (ESTIMATE: same latency, since search scope on regimens unchanged).
- If RAG/embedding reduced: minor improvement in retrieval for hybrid search (ESTIMATE <5% faster cold start for guideline metadata).
- No direct benchmark possible without temp copy of full DB (not present in working tree).

All measurements based on available JSON (clinical_data_issues, diagnosis_index) and project docs. Full normalized SQLite not present in repo (generated), so sizes for SQLite/embedding/index are ESTIMATE based on row counts and proportions. Regimen counts MEASURED from docs and verdict aggregation.

## Impact Analysis for Proposed Changes

**Change 1: Exclude LEVEL C guidelines (3 guidelines, 0 regimens) from working base (index, RAG documents, embedding scope, search metadata).**

- What changes: Remove 3 entries from diagnosis_index/guideline table; reduce RAG corpus by 3 docs; reduce embedding by ~1%; reduce guideline-related indexes.
- Tables affected: guideline (294→291), any link tables for those 3 (minimal).
- Indexes affected: indexes on guideline_id for the 3.
- Links affected: any diagnosis linked only to these 3 (check if any; likely few or none since 0 regimens).
- Can rollback: Yes (restore from original index/JSON; no data loss).
- Risk of losing medical info: None (0 regimens, no antibiotic data).
- Performance impact: Minor reduction in metadata size (~1% guideline table); negligible on search (regimens unchanged). Cold start for RAG slightly faster (ESTIMATE).
- RAG impact: 3 fewer documents to embed/retrieve.
- SQLite impact: Smaller guideline table.
- Search impact: Slightly smaller metadata to scan for guideline-level filters.

**Change 2: Flag LEVEL B guidelines (233 guidelines, 1636 regimens) for STTR queue (do not remove from current base).**

- What changes: Mark in metadata or separate queue file (simulation only); no removal.
- Tables affected: None (flagging only).
- Indexes affected: None.
- Links affected: None.
- Can rollback: N/A (no change).
- Risk of losing medical info: None (keep in base).
- Performance impact: None current.
- RAG impact: None current (still included).
- SQLite impact: None.
- Search impact: None current.

**Change 3: Reduce RAG documents to only LEVEL A + B (291 docs).**

- (Combined with 1)
- Impact as above.

No other changes proposed (no modification to regimens, parsers, etc.).

## ROI Matrix

| Change | Size DB Reduction | Search Speed | Quality Impact | Risk | ROI (size/perf vs risk) |
|--------|-------------------|--------------|----------------|------|-------------------------|
| Exclude LEVEL C (3 gid) | ~1% (guideline metadata; regimens unchanged) ESTIMATE | Negligible (regimens same) ESTIMATE | None (0 regimens lost) | None | Low (small gain) |
| Flag LEVEL B for STTR (no removal) | 0 (current) | 0 (current) | None (current) | None | High for future (enables STTR focus) |
| Reduce RAG to 291 docs | ~1% embedding/docs ESTIMATE | Minor improvement in retrieval ESTIMATE | None | None | Low |
| Reduce embedding scope | ~1% ESTIMATE | Minor cold start ESTIMATE | None | None | Low |
| Reduce SQLite (guideline table) | Small (3 rows) | Negligible | None | None | Low |
| Reduce indexes (guideline) | Small | Negligible | None | None | Low |
| Optimize search (metadata only) | N/A | Negligible | None | None | Low |

Note: Main value is focusing future work on LEVEL B via STTR rather than pruning. Pruning C gives minimal gain because C contribute 0 regimens.

## Roadmap

**Quick Wins (1–2 hours):**
- Update diagnosis_index / metadata to flag the 3 LEVEL C guidelines as non-antibiotic (for RAG filtering if implemented).
- Document the 58 LEVEL A guidelines as core (full regimens).
- Create STTR queue list for the 233 LEVEL B (flag in meta or separate JSON; no removal).

**Medium (1–2 days):**
- Manual review of LEVEL B to confirm which can be completed via STTR vs deprioritized.
- Simulate RAG/embedding rebuild with 291 docs and measure delta (on temp copy).
- Update docs (PROJECT_STATE, NEXT_TASK) with pruning simulation results.

**Long-term (separate stage, post STTR decision):**
- If STTR completes some LEVEL B → move to LEVEL A.
- Re-evaluate pruning after STTR (potential larger reduction if some B turn out non-viable).
- Only then consider actual removal of confirmed LEVEL C (with full audit and rollback plan).
- Integrate with production guard / curated index.

## Expected Gains (Summary)

- Size reduction: ~1% overall (mainly guideline metadata/RAG/embedding) ESTIMATE. Regimens and core data unchanged.
- Search acceleration: Negligible (regimens same) ESTIMATE.
- RAG: 1% fewer docs to process/embed/retrieve ESTIMATE.
- SQLite: Minimal (3 rows in guideline table).
- No loss in calculator functionality (LEVEL C contribute 0 regimens).
- Risk: None for current functionality.
- Main benefit: Cleaner base for future STTR focus on LEVEL B, reduced noise in RAG/search for non-antibiotic guidelines.

All values derived from MEASURED counts in clinical_data_issues.json and diagnosis_index.json + project docs (2675 regimens, 294 guidelines). SQLite/embedding sizes ESTIMATE (full DB not in working tree; proportions from row counts). No actual pruning performed.

**Recommendation:** Proceed with flagging only. No deletion. Wait for user decision on STTR before any larger changes. Update AI_LOG.md / PROJECT_STATE.md / NEXT_TASK.md per protocol.