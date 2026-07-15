# Knowledge Coverage Report — ANTIBIO's second core metric
## Defined 2026-07-14

> **CKY vs Coverage — do not conflate:**
> - **CKY** answers *"of the candidates we found, how many did we accept?"* (a yield / efficiency ratio).
> - **Coverage** answers *"what does the system understand at all?"* (a capability / breadth ratio).
>
> A dimension can have high CKY but low Coverage (we accept almost everything we recognize, but we
> recognize it in very few guidelines) — or the reverse. Both are needed. Coverage is the second
> north-star metric alongside `CLINICAL_KNOWLEDGE_YIELD.md`.

## Definitions

Two coverage numbers per clinical dimension, across the corpus of source guidelines/PDFs:

```
Recognition Coverage[dim] = (# guidelines where the system RECOGNIZES ≥1 candidate of dim)
                            / (# guidelines)

Delivered   Coverage[dim] = (# guidelines where ≥1 accepted KB object of dim exists)
                            / (# guidelines)
```

- **Recognition** = capability: can the pipeline even perceive this kind of fact in this document?
- **Delivered** = realized: does that fact actually survive to the Knowledge Base?
- **Recognition − Delivered = the loss surface** for that dimension (explained by the PR-008
  ranked loss histogram + which Root Cause is responsible).

## Dimensions (same axes as CKY)

`drug · dose · duration · route · frequency · alternatives · first_line · pediatric · pregnancy ·
renal · contraindications · evidence`

Illustrative target shape (real numbers come from the post-rebuild run — NOT asserted here):

```
Drug            98%
Dose            95%
Duration        92%
Route           91%
Alternatives    34%   ← low delivered coverage → RC-009 (KB builder drops AlternativeTherapy)
Pregnancy       18%
Renal           12%
Evidence         5%
```

Low coverage on **safety axes** (pediatric / pregnancy / renal) is a production-readiness red flag,
even if overall CKY looks healthy.

## How it is measured
- **Delivered coverage:** `python -m src.pipeline.knowledge_coverage --db kb_p44.db` — pure SQL over
  the KB (`objects` + `provenance.pdf`), cheap, runs against the full corpus KB.
- **Recognition coverage:** derived from `semantic_yield_audit.py` candidate counts per guideline
  (requires re-running semantic; run on a representative set or full corpus as budget allows).
- Both are recorded as benchmark snapshots in `PRODUCTION_READINESS_PROGRAM.md` and `AI_LOG.md`.

## Relationship to the platform
- Coverage + CKY together drive Root Cause ranking: a dimension with high recognition but low
  delivered coverage is a high-benefit / low-effort fix (the facts are already perceived — only the
  downstream drop needs fixing, e.g. RC-009).
- Coverage on safety axes is a **milestone-closure gate** (see governance Definition of Done).
