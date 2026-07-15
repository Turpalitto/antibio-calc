# Provenance Contract Matrix — semantic → Knowledge Object → SQLite
## Complete contract audit · 2026-07-14 · prerequisite to the unified RC-012/013 migration

> The semantic entity provenance dict, the `Provenance` dataclass, and the `provenance` SQLite
> table are ONE contract. This matrix verifies every field end-to-end (Producer → Consumer →
> Storage → Validation → Usage → Backward-compat) so the contract is fixed **once**. Do not
> implement RC-012/013 until this matrix is accepted.

## Sides of the contract
- **Producer** — entity `provenance` dict emitted by `semantic.py`:
  - flat text (`_mk_ent`): `{page, engine, source, coordinates}`
  - table cell (`extract_entities_from_tables`): `{page, engine, source, row, col, bbox, table_conf}`
- **Consumer** — `knowledge_base.add_document` builds a `Provenance(...)` from `src` (= the entity
  provenance dict) and from the knowledge-object `item`.
- **Storage** — `Provenance` dataclass (14 fields) → `provenance` table via `_add_provenance` INSERT
  (15 columns) over a base table (7 cols) + 9 migrated cols.

---

## Field-by-field matrix

| # | Field (dataclass/column) | Producer (actual) | Consumer binding | Stored? | Status |
|---|--------------------------|-------------------|------------------|:------:|--------|
| 1 | `pdf` | `doc.pdf_path` | `pdf_name` | ✅ | **OK** |
| 2 | `guideline_id` | — *(never emitted)* | `src.get("guideline_id")` → None | ✅(null) | **RC-013** producer never sets it |
| 3 | `page` | `page` | `src.get("page", src.get("page_num",0))` | ✅ | **OK** |
| 4 | `paragraph` | — *(never emitted)* | `src.get("paragraph")` → None | ✅(null) | **RC-013** producer never sets it |
| 5 | `bounding_box` | `bbox` (table only) | `src.get("bbox") or src.get("bounding_box")` | ✅ | **OK** (null for free-text, expected) |
| 6 | `extractor` | `doc.source` | `doc.source or "router"` | ✅ | **OK** |
| 7 | `layout_engine` | producer emits `engine` (ignored) | inferred: `"doclayout-yolo" if "table" in source else "none"` | ✅ | **RC-014** heuristic mislabels; real engine is `table-transformer+rapidtable`; producer's `engine` ignored |
| 8 | `semantic_engine` | — | literal `"semantic+table"/"semantic.py"` by string match on source | ✅ | **RC-014** inferred, not sourced |
| 9 | `table_row` | `row` (table only) | `src.get("row")` | ✅ | **OK** |
| 10 | `table_col` | `col` (table only) | `src.get("col")` | ✅ | **OK** |
| 11 | `original_text` | — *(item has `raw`, not `text`)* | `src.get("original_text") or item.get("text")` → None | ✅(null) | **RC-012** key mismatch `raw`≠`text` |
| 12 | `normalized_value` | — | `src.get("normalized_value") or item.get("normalized")` | ✅ | **OK but fragile** (works only via `item` fallback) |
| 13 | `timestamp` | `now` | `now` | ✅ | **OK** |
| 14 | `doc_version` | hardcoded `"p4.4-2026-07"` | constant | ✅ | **OK** (constant; not source-derived) |

### Producer keys emitted but never consumed (silent drops)
- `engine` — the actual extraction engine per entity → **ignored** (consumer infers instead → RC-014).
- `coordinates` (flat text) — always None anyway.
- `table_conf` — table confidence, a real quality signal → **dropped entirely** (RC-014 scope).

### Storage-level defect
- **RC-015** — base `CREATE TABLE provenance` declares column **`semantic`**, but the INSERT writes
  **`semantic_engine`** (a migrated column). `semantic` is never written → dead legacy column.

---

## Consolidated findings (all one contract)
| ID | Defect | Fix in the unified migration |
|----|--------|------------------------------|
| RC-012 | `original_text` null (raw≠text) | consumer reads `item.get("raw")`; producer also stamps `original_text` on the entity prov |
| RC-013 | `guideline_id` + `paragraph` never produced | producer threads `guideline_id` (from `doc.metadata`) + `paragraph` into entity prov |
| RC-014 | engine mislabeled (heuristic); `engine`/`table_conf` dropped | consumer reads producer's real `engine`; carry `table_conf` (add column) |
| RC-015 | dead `semantic` column | drop/normalize schema to `semantic_engine` only |

## Unified migration principles (fix once)
1. **One canonical provenance vocabulary** shared by producer and consumer — no key ever written
   under one name and read under another. Define it in ONE place (a small `to_provenance_dict()`
   helper or documented key set).
2. **Producer completeness:** the semantic layer stamps `guideline_id`, `paragraph`,
   `original_text`, `engine`, `table_conf` at emission — the consumer only maps, never infers.
3. **One schema change** adds any missing columns (`table_conf`) and retires `semantic` in the same
   migration; version the provenance schema.
4. **Backward compatibility:** existing rows keep working (nullable new columns); a single KB
   re-run backfills correct values. No second migration for the same contract.
5. **Invariant coverage:** after the migration, INV-09 (original wording) passes, and add
   INV-15 (every provenance has a real `engine`, not an inferred placeholder) + INV-16 (guideline_id
   present for corpus PDFs).

## Gate
No RC-012/013/014/015 code change ships until this matrix is accepted and the migration is designed
as **one** change. This is recorded as the single provenance-contract remediation in the Root Cause
Register.
