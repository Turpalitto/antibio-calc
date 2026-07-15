# REVIEW_PACKET_CONTRACT.md
## Canonical Review-Packet Provenance Contract · P5.6 RC-027 Phase 2

> Fixes the root cause in `RC027_ROOT_CAUSE_REPORT.md`: one documented precedence order, read by
> ONE canonical mapper, tolerant of every real provenance-dict shape already in production storage
> (no re-ingestion required).

## Required fields on every review packet
| Field | Source | Required |
|---|---|:---:|
| `original_source_wording` | resolved per §Precedence below | Yes (or explicit `MISSING`) |
| `normalized_value` | target payload's own normalized field (`drug_normalized`/`therapeutic_class` etc.) | When applicable |
| `source_quote` | target's own `source_quote` field (payload-level, not per-field) | Yes, when the target type has one |
| `guideline_id` | target payload / source_references | Yes |
| `guideline_version` | **not currently modeled anywhere in the repository** — no producer emits it | N/A — report `UNAVAILABLE`, never fabricate |
| `source_pdf` | `source_references[].pdf` | Yes |
| `page` | `source_references[].page` or per-field `source_location` | Yes |
| `paragraph` | per-field provenance, when the underlying kb_p44 object carries `paragraph` | When available |
| `bounding_box` | kb_p44 `Provenance.bounding_box`, when the field traces to a kb_p44 object | When available |
| `table_row` / `table_col` | kb_p44 `Provenance.table_row/table_col`, when applicable | When available |
| `extractor` | kb_p44 `Provenance.extractor`, when applicable | When available |
| `layout_engine` / `semantic_engine` | kb_p44 `Provenance`, when applicable | When available |
| `target_object_id` / `target_object_version` | `task.target_id` / `task.target_version` | Yes, always |

## Precedence — explicit, ordered, documented (fixes the mapping bug without a schema change)
For each provenance entry, `original_source_wording` resolves via the FIRST match in this order:
1. **Field-level `original_text`** — if a provenance dict literally has this key (future producers
   may add it), use it.
2. **Field-level `source_quote`** — the shape `ClinicalDataIssue`'s working producers already use
   (`{"source_quote": ...}`) — covers `DOSE_NOT_EXTRACTED`/`DOSE_NOT_PARSED`/`DOSE_DAILY_MISREAD`/
   `DOSE_UNIT_GROUP` (already correct today; unchanged by this fix).
3. **Target-level `source_quote`** — the target payload's OWN `source_quote` field (present on
   every `ClinicalRegimen` and `TherapeuticOption`, confirmed 100% populated) — this is the
   precedence tier that RC-027 was missing entirely; closes the `ClinicalRegimen`/`TherapeuticOption`
   gap (2,208 of the 2,215 RC-027-scoped tasks).
4. **Golden-case `source` field** (`case.provenance.source`, per `golden_cases/schema.json`) — closes
   the remaining 7 `GoldenCase` tasks.
5. **Unavailable** — if none of the above resolve to a non-empty string, the field is explicitly
   `MISSING` (see below). **Never fabricated, never inferred, never defaulted to placeholder text.**

## Explicit missing-state contract
```
source_wording_status = "MISSING"
review_blocked = true
```
Set when precedence tiers 1-4 all fail to produce a non-empty string for a given provenance entry.
`review_blocked=true` on the PACKET (not silently per-field) whenever `original_source_wording`
resolves to `MISSING` for the ONLY or PRIMARY source reference — a reviewer must never be asked to
approve a clinical fact they cannot see the source text for. This is fail-closed by construction:
absence of wording blocks review rather than silently passing an unverifiable packet.

## What this contract explicitly does NOT cover (see RC027_ROOT_CAUSE_REPORT.md §Scope)
`ConflictRecord` and `CorpusExclusionDecision` packets, whose `provenance` is `[]` by design (no
per-field provenance concept was ever built for them). Under this contract they resolve to tier 5
(`MISSING`) honestly — which is **correct, not a regression**: there genuinely is no field-level
quoted excerpt to show for these two target types today. `source_references` (guideline ids / pdf +
locations) still reaches the packet independently of this contract and remains visible to reviewers.
Closing that gap is a separate, future root cause — not folded into RC-027.

## Multiple source excerpts
A target may have more than one provenance entry (one per enriched field). The contract preserves
**one resolved wording string per provenance entry**, in the SAME deterministic order the entries
appear in storage (no re-sorting, no deduplication that could hide a genuine second citation) —
satisfies "multiple source quotations preserved" (Phase 3 requirement) without inventing a new
aggregation step.
