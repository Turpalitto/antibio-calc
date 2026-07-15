# KNOWLEDGE_TO_REGIMEN_PIPELINE.md
## Knowledge → Regimen → Recommendation Pipeline & Provenance Chain · P5.1
## Status: PROPOSED (design only)

> The end-to-end flow and the unbroken provenance chain from source PDF to clinical recommendation.
> Ties `CLINICAL_REGIMEN_MODEL.md` (what) and `REGIMEN_ASSEMBLY_ENGINE_RFC.md` (how) into the full
> path. Read alongside P5.0's `P5_MIGRATION_MASTER_PLAN.md` (which covers the store-level flow).

## 1. The full pipeline
```
PDF (КР, clinrec)
  │  rule-based layout extraction (P4.4: PyMuPDF + DocLayout-YOLO + Table Transformer)
  │  AND/OR LLM extraction (main.py: extract_raw → validate)
  ▼
Atomic Knowledge Objects (kb_p44: Dose, Medication, Contraindication, Evidence, Diagnosis)
  │  each with full Provenance v2 (pdf, page, table_row/col/conf, original_text, guideline_id)
  ▼
Regimen Assembly Engine (P5.1 — deterministic, ruleset-versioned)
  │  group → resolve fields → link alternatives → resolve conflicts → assemble provenance
  ▼
ClinicalRegimen aggregates (versioned, immutable, with assembly_trace)
  │  Validation Gates (REGIMEN_VALIDATION_GATES.md): required-fields → safety → human review → approval
  ▼
Approved ClinicalRegimen (validation_verdict=PASS, approved=1)
  │  CanonicalStoreRegimenProvider (CLINICAL_ENGINE_ADAPTER_RFC.md) — projects to RecommendationCandidate
  ▼
Clinical Decision Engine (frozen, 10-stage recommend() pipeline)
  ▼
RecommendationSet → physician
```

## 2. The provenance chain (unbroken, per the mandate's Phase 6)
The mandate requires the chain: **PDF → page → table/cell → knowledge object → regimen → clinical
recommendation.** This is achievable today because each link already exists or is designed here:

| Link | Mechanism | Status |
|---|---|---|
| PDF → page | kb_p44 Provenance `pdf` + `page` | EXISTS (certified 2026-07-15, 0 nulls) |
| page → table/cell | kb_p44 Provenance `table_row`, `table_col`, `table_conf` | EXISTS (INV-17 verified) |
| table/cell → knowledge object | kb_p44 object ↔ its provenance row (INV-01/02) | EXISTS |
| knowledge object → regimen | `ClinicalRegimen.assembly_trace.constituent_object_ids` + `field_sources` | **NEW (this design)** — every regimen field names the kb_p44 object it came from |
| regimen → clinical recommendation | `RecommendationCandidate.regimen_id` (already carried by the engine on every candidate) | EXISTS (engine already keys on regimen_id; `clinical_engine/corpus/provenance.py` already resolves regimen_id → source) |

**Key property:** the chain has no heuristic hop. At assembly, each regimen field records the exact
object id it resolved from (Assembly RFC §6); each object records its exact cell (Provenance v2).
So "why this dose for this recommendation?" resolves: recommendation → regimen_id → regimen →
field_sources[dose] → kb_p44 Dose object → provenance → pdf/page/cell/original_text. No gaps, no
inference — the same standard the P4.4 certification already meets, extended one link upward.

## 3. Determinism of the chain
Because assembly is a pure function of (kb_p44 snapshot, ruleset version), and the engine is
deterministic given its input, the ENTIRE chain from PDF-derived objects to recommendation is
reproducible from two version anchors: `snapshot_version` (which kb_p44 build) and
`assembly_ruleset_version` (which assembly logic). An auditor can replay any historical
recommendation exactly by pinning both. This is the regulatory-replay property a certified CDSS
needs.

## 4. Cross-check against the engine's existing provenance resolver
`clinical_engine/corpus/provenance.py` already independently resolves `regimen_id → source PDF`
(SHA-256 verified). During migration this is a FREE correctness check: for the same `regimen_id`,
the new assembly provenance chain and the existing corpus resolver must agree on (pdf, page,
guideline_id). Divergence = a real defect surfaced before cutover. Do not discard the old resolver
until this cross-check has run clean across the full corpus (echoes MR-9 in `RISK_REGISTER.md`).

## 5. Where the two extraction methods enter
- Rule-based (P4.4) atomic facts feed assembly directly — strongest for table-derived dose/route
  cells.
- LLM-extracted regimens (`metadata.sqlite::antibiotic_regimens`) enter as either (a) pre-assembled
  regimens mapped to `ClinicalRegimen` directly, or (b) decomposed into atomic facts that flow
  through assembly like any other — **decision deferred** to migration (MIGRATION_PLAN), because it
  depends on whether the LLM output's granularity is trusted as-is or re-assembled for uniformity.
  Either way, provenance records which extractor produced each fact.

## 6. Failure handling (no silent loss — the RC-001 lesson generalized)
Any break in the chain during assembly (a field with no traceable source object, a regimen whose
constituent objects span inconsistent guidelines, a conflict that cannot be resolved) does not
produce a silently-defaulted regimen. It produces a regimen flagged `REVIEW`/`REJECT` with the break
recorded in `assembly_trace`. The chain is either complete or the regimen is quarantined — never
served with a gap. This is the same fail-loud principle that PR-001 and RC-017 were about, applied
to the assembly layer.
