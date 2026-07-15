# Clinical Knowledge Yield (CKY) — ANTIBIO's north-star metric
## Defined 2026-07-14

> **Why CKY:** "29 tables → 4 objects" is not a metric — it can't be compared across changes. CKY
> makes clinical-knowledge extraction *objectively measurable*, so every pipeline change can be
> judged by whether it raises or lowers real yield. CKY is the primary optimization target of the
> Root Cause Program (`ROOT_CAUSE_REGISTER.md`) — maximize CKY while preserving traceability,
> determinism, and reproducibility.

## Definition

```
CKY = Accepted Knowledge Objects / All Clinically-Relevant Candidates
```

- **Clinically-relevant candidate:** a table/text-derived entity of a clinical type (drug, dose,
  frequency, duration, route, alternative, first-line, pediatric/weight, pregnancy, renal,
  contraindication, evidence) that a physician would consider real information.
- **Accepted Knowledge Object:** a candidate that reaches the Knowledge Base as an active, valid,
  provenance-carrying object (not deduped-away, not dropped by the builder, not validation-failed).

CKY is always reported **with its funnel and loss histogram** (from `semantic_yield_audit.py`), so
a number is never presented without the *why* behind it:

```
164 clinical candidates → 121 valid → 104 accepted     CKY = 63% (104/164)
```

## Dimensions (report all)

Overall CKY plus per clinically-meaningful axis — because a high overall CKY can still hide a
near-zero yield on a safety-critical axis (e.g. pregnancy/renal):

| Dimension | What it measures |
|-----------|------------------|
| `CKY.overall` | all clinical candidates → accepted objects |
| `CKY.antibiotics` | drug/medication candidates |
| `CKY.dose` | dose candidates |
| `CKY.duration` | duration candidates |
| `CKY.frequency` | frequency candidates |
| `CKY.alternatives` | AlternativeTherapy candidates |
| `CKY.first_line` | FirstLineTherapy candidates |
| `CKY.pediatric` | pediatric / weight-stratified candidates |
| `CKY.pregnancy` | pregnancy candidates |
| `CKY.renal` | renal-adjustment candidates |
| `CKY.contraindications` | contraindication candidates |
| `CKY.evidence` | evidence-level / strength candidates |

## Rules
- **Never report CKY without the loss histogram** (per-reason breakdown from PR-008).
- **CKY is a ratio, not a count** — it stays comparable as the corpus grows.
- **Safety axes gate closure:** pediatric / pregnancy / renal CKY are reported explicitly; a milestone
  cannot be called production-ready if a safety axis silently yields ~0.
- **CKY is measured on real corpus execution only** — no synthetic candidates, no mocked runs.
- Every Root Cause fix records its **CKY before → after** delta (benchmark policy).

## Source of truth
`src/pipeline/extraction/semantic_yield_audit.py` computes the funnel, the per-reason loss
histogram, and CKY (overall + per dimension). Its JSON output is the benchmark artifact; snapshots
are recorded in `PRODUCTION_READINESS_PROGRAM.md` and `AI_LOG.md`.
