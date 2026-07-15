# SINGLE_SOURCE_OF_TRUTH_RFC.md
## RFC — Canonical Knowledge Storage for ANTIBIO · P5.0 · Phase 3
## Status: PROPOSED (documentation only, no implementation)

> Prerequisite reading: `EXECUTIVE_SUMMARY.md` Phase 1 (current-state grounding). This RFC does not
> repeat that grounding; it builds the SSOT decision on top of it.

## 1. The real choice (not "kb_p44 vs normalized_regimens")
The naive framing — "two databases, pick one" — is wrong. The two stores differ on two independent
axes that must be resolved separately:

| Axis | `kb_p44.db` (P4.4) | `normalized_regimens.sqlite` |
|---|---|---|
| **Granularity** | Atomic fact (one `Dose`, one `Medication`, one `Contraindication` object each) | Bundled regimen (one row = a complete antibiotic+dose+route+frequency+duration+population+pregnancy+renal recommendation unit) |
| **Extraction method** | Rule-based: PyMuPDF text + DocLayout-YOLO/Table-Transformer layout + regex/dictionary semantic entities. No LLM. | LLM two-pass extract+validate (`extractor_llm.py`), then deterministic normalization (`medical_normalizer`, FROZEN). |
| **Provenance rigor (measured)** | Certified 2026-07-15: 100,854 rows, 0 silent nulls, 0 blocking invariant violations, schema-versioned (`schema_version=2`). | Has its own resolver (`clinical_engine/corpus/provenance.py`), SHA-256-verified back to source PDF, but not audited to the same invariant discipline this session applied to `kb_p44`. |
| **Review/lifecycle fields** | `status` (currently non-canonical `active`/`superseded`, see RC-022), `validation_status`, `review_status`. | `review_status`, `reviewed_by`, `review_date`, `approved`, `manual_override` — **already has a human-in-the-loop review model wired in the schema**, unused/unpopulated status unknown (not verified this pass — mark UNKNOWN). |
| **Consumer today** | Nothing (orphaned, per EAR-1). | The Clinical Decision Engine, exclusively, via the frozen spec's `SQLiteReader`. |
| **Yield (measured)** | `CKY.overall=10.3%` on the representative sample; `CKY.tables=1.1%` (RC-009: bundled therapy-line/alternative/pediatric facts largely dropped by the KB builder). | Row count is 100% of what the LLM pipeline extracted+validated (2,675/2,675 `validated=1`) — different metric (extract-validate acceptance, not KB-ingestion yield), not directly comparable to CKY without a shared denominator. Mark comparison **UNKNOWN** pending a joint audit. |

**Two independent decisions, not one:**
- **Decision A — which extraction methodology is authoritative per data class** (tables → rule-based
  layout pipeline measurably works, CKY on non-table free text is higher; regimen-level prose
  synthesis → LLM pipeline is the only one that currently produces it at all).
- **Decision B — which storage/provenance CONTRACT is authoritative** (kb_p44's contract — spec,
  invariants, schema versioning — is the one this project just spent a full session hardening and
  independently auditing; it should govern regardless of which extractor fills it).

## 2. Recommendation
**The canonical storage CONTRACT is `kb_p44`'s Knowledge Object + Provenance model
(`PROVENANCE_SPECIFICATION.md`, `ARCHITECTURAL_INVARIANTS.md`), extended with one new first-class
object type: `Regimen`** — a bundle object referencing its constituent atomic facts
(Drug/Dose/Frequency/Route/Duration/Contraindication/AgeRestriction/etc. by id) plus the fields
`RecommendationCandidate` needs that have no atomic-fact equivalent today (`therapy_line`,
`validation_verdict`, `review_status`/`reviewed_by`/`approved`, `guideline_year`).

**Both extraction pipelines write into this one contract:**
- The rule-based P4.4 pipeline continues producing atomic facts (its measured strength: tables,
  structured cells, this session's whole provenance investment).
- The LLM pipeline's `extract_regimens`/`validate_regimens` output is mapped into `Regimen` objects
  (its measured strength: whole-regimen synthesis from prose, 100% validated today) instead of its
  own separate `metadata.sqlite`/`normalized_regimens.sqlite` schema.
- A `Regimen` object's provenance MUST reference the atomic facts it was assembled from where they
  exist (traceability down to the cell/quote level, per `PROVENANCE_SPECIFICATION.md`), and MUST
  carry its own direct provenance (pdf/page/quote) when assembled by the LLM path with no
  corresponding atomic P4.4 fact (expected initially, given `CKY.tables=1.1%`).

**Why not the reverse (make `normalized_regimens.sqlite` canonical, wrap kb_p44 as a cache)?**
Rejected. `normalized_regimens.sqlite`'s schema, while mature, was never subjected to the
invariant/CKY/coverage audit discipline this session built and validated at full corpus scale; its
provenance resolver, while real, is a bespoke one-off (`corpus/provenance.py`) rather than a
governed, versioned contract (`schema_version`, `INV-01..17`) with a reusable checker
(`knowledge_invariants.py`). Making it canonical would mean re-deriving everything `kb_p44` already
has, on a schema not designed for atomic-fact traceability (no `table_row`/`table_col`/`table_conf`
equivalents). It also means throwing away the P4.4 certification's work rather than building on it.

**Why not "keep both forever, never converge" (status quo)?**
Rejected as the end-state (though it is the correct *transitional* state — see Migration RFC). Two
independently-evolving knowledge models for the same clinical domain is the textbook drift risk
EAR-1/EAR-7 named: a guideline update applied to one pipeline and not the other silently produces
inconsistent recommendations between what P4.4 "knows" and what the engine serves, with no
mechanism to detect the divergence. `RC-011`'s substring-based dedup and `RC-022`'s status drift
compound this if left unaddressed indefinitely.

## 3. What becomes cache / adapter / compatibility layer / removed
| Component | Disposition |
|---|---|
| `medical_normalizer` package (parsers, confidence, validator) | **Keep as a normalization LIBRARY**, called by the ingestion path that writes `Regimen` objects into the canonical store. Not removed — its logic has no P4.4 equivalent. |
| `normalized_regimens.sqlite` (the file) | **Becomes a generated read-projection** (optional, for the transition window only) rebuilt FROM the canonical store; retired once the engine's adapter (see `CLINICAL_ENGINE_ADAPTER_RFC.md`) reads the canonical store directly. |
| `metadata.sqlite::antibiotic_regimens` | **Becomes ingestion staging**, not a serving store — the LLM pipeline's raw+validated output before it is mapped into canonical `Regimen` objects. Compatible with today's `main.py`/`src/pipeline/main.py knowledge` command as-is. |
| `clinical_engine/corpus/provenance.py` | **Superseded** by the canonical store's provenance contract once `Regimen` objects carry it natively; kept temporarily as a compatibility/cross-check tool during migration (compare its resolved chain against the canonical provenance for the same `regimen_id` — a free correctness check). |
| `kb_p44.db` atomic objects | **Remain first-class**, unchanged in model; gain a new relationship (`Regimen.constituent_fact_ids`) pointing to them. |

## 4. Governance interaction
The Clinical Decision Engine's logic and the frozen spec (`docs/superpowers/specs/
clinical-decision-engine-v1.md`) are **not** touched by this RFC. `RecommendationCandidate`'s field
shape is the CONTRACT the new `Regimen`-to-candidate mapping must satisfy exactly (see
`CLINICAL_ENGINE_ADAPTER_RFC.md`) — this RFC constrains the storage layer to serve that contract,
not the reverse. Any field `RecommendationCandidate` needs that `Regimen` cannot supply is a
blocking gap to resolve before cutover, not a reason to alter the frozen model.
