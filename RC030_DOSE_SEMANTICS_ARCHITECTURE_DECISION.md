# RC-030 — Where Should Explicit Dose Semantics Live? Architecture Decision

## Options evaluated

**A. Extraction layer.** Capture `denominator_time` (and max-dose) at the moment text is pulled from the PDF, before normalization or assembly. Highest-fidelity source access (raw layout, table structure still available) but requires re-running extraction across all 192 source PDFs — the most expensive option, and it duplicates work the P5.3 assembly pipeline already does downstream.

**B. Normalizer layer.** Add the field during `medical_normalizer` processing, where `source_quote` is already carried per-row. Cheaper than A (no PDF re-extraction), but the normalizer's job today is field-level normalization (units, synonyms), not semantic disambiguation of what a number modifies — this would expand its responsibility significantly and still requires reprocessing all 2,675 existing normalized rows.

**C. Canonical assembly layer.** Add `denominator_time` (and max-dose columns) to `assembled_regimens` at the P5.3 assembly step, backfilled from `source_quote` using logic equivalent to today's sandbox parser. This is the schema fix the original RC-030 finding actually calls for (`RC030_SCHEMA_RESPONSIBILITY_DECISION.md`, referenced from `ROOT_CAUSE_REGISTER.md`) — it puts the field where every downstream consumer (Clinical Engine, Review Workbench, this sandbox) already looks for regimen data, with a normal schema migration + backfill, versioned like every other assembled field.

**D. Additive semantics layer (current sandbox approach).** Keep `dose_verification_sandbox/semantics_*.py` as a read-only reconstruction on top of the untouched schema, as it exists today. Zero schema risk, zero migration cost, fully reversible (delete the sandbox, nothing else changes) — but it is explicitly a workaround: every consumer that wants semantics has to re-derive them from `source_quote` at read time instead of reading a column, and the underlying schema gap that caused RC-030 in the first place remains unfixed for any future assembly run.

**E. Hybrid.** Ship D now (already done — this is what's committed), and treat C as the tracked, separately-scoped follow-up (already exists as an open item: RC-030's `ROOT_CAUSE_REGISTER.md` entry explicitly names "Architecture Change (assembly-engine schema: add `denominator_time` and max-dose columns, backfill from `source_quote`)" as the real fix, with the sandbox parser as an interim reconstruction).

## Evaluation

| Criterion | A | B | C | D | E |
|---|---|---|---|---|---|
| Future extraction quality | Best | Good | Neutral | Neutral | Neutral now, best when C lands |
| Historical rebuild cost | Full 192-PDF re-extraction | Full 2,675-row renormalization | Schema migration + backfill only | None | None now, deferred cost later |
| Source provenance | Preserved natively | Preserved via `source_quote` | Preserved via `field_provenance` (existing pattern) | Reconstructed at read time | Both |
| Versioning | New extraction version needed | New normalizer version needed | Fits existing `assembly_ruleset_version` pattern | `semantic_version` internal to sandbox only | Both |
| Backward compatibility | Breaks extraction consumers | Breaks normalizer consumers | Additive columns, non-breaking | Fully additive, zero risk | Fully additive now |
| Conflict handling (existing rows) | N/A (rebuild) | N/A (rebuild) | Backfill script, reviewable | N/A (no schema change) | N/A now |
| Table inheritance (header→row) | Handled at source | Not this layer's job | Handled at assembly, where table structure is already flattened | Cannot recover — sandbox only sees flattened `source_quote` | Same as D until C |
| Cost to rebuild 2,675 rows | Very high | High | Medium (backfill only) | None | None now |
| Impact on Clinical Engine | Requires re-integration | Requires re-integration | New nullable columns, opt-in | None — sandbox stays disconnected | None now |
| Auditability | Good | Good | Best (single source of truth) | Weaker (logic duplicated wherever needed) | Best over time |

## Decision

**E (hybrid), already in effect.** No schema change is proposed or made in this task — `assembled_regimens.sqlite` is not mutated. The sandbox (D) is the correct interim state given RC-030 is still `CALCULATION_BLOCKED` and unvalidated; committing to a schema migration (C) before the sandbox's parser has cleared any precision threshold would mean migrating the schema around logic that hasn't been proven correct. The recommended trigger for actually doing C: once `TYPES_MEETING_PRECISION_THRESHOLD` gains at least one entry (i.e., some semantic type clears the 99% Wilson-lower-bound bar through real human validation), re-evaluate whether that type's resolution logic is stable enough to promote into a real assembly-layer column.

No mutation to `assembled_regimens.sqlite` was made or is proposed as part of this decision.
