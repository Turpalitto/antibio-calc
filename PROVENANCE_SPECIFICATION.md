# PROVENANCE_SPECIFICATION.md
## Canonical Provenance Contract — ANTIBIO · VERSION 1.0 · 2026-07-14

> Single authoritative specification for provenance across `semantic → KnowledgeObject → SQLite`.
> Code conforms to THIS document, not the reverse. Supersedes ad-hoc field handling and the
> individual fixes RC-012/013/014/015 (all symptoms of one contract defect: producer and consumer
> used different key vocabularies).
>
> **Founding rule — One canonical vocabulary:** the provenance dict emitted by the semantic layer
> MUST use the **exact `Provenance` dataclass field names**. The consumer (`add_document`) then
> maps 1:1 and MUST NOT infer, guess, or reconstruct any field. One field · one meaning · one owner
> · one name everywhere.

## Provenance schema version
`provenance_schema_version = 2` (v1 = pre-2026-07-14 heuristic contract). Stored in
`provenance.doc_version` companion field `schema_version` (added by the unified migration).

---

## Field specification

Legend — Required: **R** (must be present & non-null when applicable) · **O** (optional) ·
Owner = the single layer responsible for producing the value.

| Field | Type | Req | Default | Owner (Producer) | Consumer | SQLite column | Validation / Allowed | Notes |
|-------|------|:---:|---------|------------------|----------|---------------|----------------------|-------|
| `pdf` | str | R | — | Document (pdf_path) | map | `pdf` | non-empty | source file |
| `guideline_id` | str? | R* | None | Document metadata (pdf→guideline via knowledge_base.json `pdf_file`) | map | `guideline_id` | present for corpus PDFs | *R when the PDF maps to a known guideline |
| `page` | int | R | 0 | Extraction/Layout | map | `page` | ≥0 | 0-indexed |
| `paragraph` | str? | O | None | Semantic (section/layout block id) | map | `paragraph` | — | best-effort; O until layout paragraphs exist |
| `bounding_box` | dict? | O | None | Layout | map | `bounding_box` (JSON) | {x0,y0,x1,y1} | table/layout-derived only |
| `extractor` | str | R | "router" | Extraction (doc.source) | map | `extractor` | non-empty | e.g. pymupdf/router |
| `layout_engine` | str | R | "none" | Layout | map | `layout_engine` | real engine or "none" | e.g. `table-transformer+rapidtable`, `doclayout-yolo`; **never inferred** |
| `semantic_engine` | str | R | "semantic.py" | Semantic | map | `semantic_engine` | `semantic.py` / `semantic+table` | set explicitly by semantic layer |
| `table_row` | int? | R‡ | None | Layout | map | `table_row` | ≥0 | ‡R for table-derived objects |
| `table_col` | int? | R‡ | None | Layout | map | `table_col` | ≥0 | ‡R for table-derived objects |
| `table_conf` | float? | O | None | Layout | map | `table_conf` **(new col)** | 0..1 | table confidence; previously dropped (RC-014) |
| `original_text` | str | R | — | Semantic | map | `original_text` | non-empty | raw wording; **never discarded** (Clinical Governance) |
| `normalized_value` | str? | O | None | Semantic | map | `normalized_value` | — | normalized form |
| `timestamp` | str | R | now | Knowledge Builder | set | `timestamp` | ISO-8601 | write time |
| `doc_version` | str | R | "p4.4-2026-07" | Document | set | `doc_version` | — | KB build version |
| `schema_version` | int | R | 2 | Knowledge Builder | set | `schema_version` **(new col)** | =2 | provenance contract version |

**Retired:** legacy base column `semantic` (RC-015) — dropped/ignored; `semantic_engine` is canonical.

---

## Ownership rules (Phase 3)
- A field is produced by exactly **one** owner (table above). No field may be inferred downstream if
  an upstream owner can emit it.
- `layout_engine` / `semantic_engine` / `table_conf` are emitted by the layer that actually ran —
  **never** reconstructed by string-matching `source` in the consumer (this was RC-014).
- `original_text` is emitted by the semantic layer as the entity's raw wording (canonical key
  `original_text`), independent of any `raw`/`text`/`name` key used internally (this was RC-012).
- `guideline_id` is resolved once at document level from the pdf→guideline map and stamped onto
  every entity's provenance (this was RC-013).

## Consumer rules (Phase 4 — remove heuristics)
`add_document` MUST build `Provenance(**{f: prov[f] for f in FIELDS if f in prov})` plus the
Builder-set fields (`timestamp`, `doc_version`, `schema_version`) and doc-level `pdf`. It MUST NOT:
- read a field under a different name than the producer wrote it,
- infer `layout_engine`/`semantic_engine` from `source`,
- fall back to unrelated keys (`item.get("text")`) to populate provenance.

## Serialization / Deserialization
- `Provenance.to_dict()` = `asdict` (all fields). `bounding_box` serialized as JSON in SQLite.
- Round-trip invariant: `from_row(to_row(p)) == p` for all fields (new test).

## Backward compatibility & migration (Phase 6/7)
- One **atomic** migration (in `KnowledgeBase._migrate`): add columns `table_conf`, `schema_version`.
  Legacy `semantic` is left in place but **never written (documented-dead)**. Engineering decision:
  dropping a column in SQLite requires a full table rebuild (copy → drop → rename) with real risk
  and no functional benefit, since the column is already ignored. Documented-dead is the lower-risk,
  spec-compliant choice.
- Existing v1 rows: `schema_version` backfilled to 1; they remain readable. A full KB re-run
  regenerates v2 rows with correct values. No second migration for this contract.
- Forward compat: unknown future provenance keys are ignored by the 1:1 mapper (I10-style).

## Invariants added by this spec (Phase 10)
- **INV-09** original wording preserved (already exists; passes after migration).
- **INV-15** every provenance has a real `layout_engine`/`semantic_engine` (no inferred placeholder
  for layout/table-derived objects).
- **INV-16** `guideline_id` present for every object whose PDF maps to a known guideline.
- **INV-17** every table-derived object preserves `table_conf` (non-null when table_row present).

## Acceptance question (Phase 12)
The contract is satisfied only when: *"every Knowledge Object can be traced to its exact origin —
pdf, page, guideline, engine, table cell, original wording — without heuristics, without ambiguity,
without information loss."* Answer must be an evidence-based YES (invariants + provenance audit),
else the contract stays OPEN.
