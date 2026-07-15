# INT-5 — Public API Architecture Review

**Status:** Architecture review — APPROVED with adjustments. Implementation NOT started.
**Date:** 2026-07-11
**Scope:** Defines the stable public contract for the Clinical Decision Platform. No code, no calculator changes.

> This document is the authoritative contract reference for INT-5. It supersedes the
> in-chat review. Implementation begins only after explicit approval of this file.

---

## 0. Context — from calculator to Clinical Decision Platform

The system is no longer an antibiotic calculator; it is a Clinical Decision Platform with one
medical brain and many thin clients:

```
Clinical Guidelines (КР МЗ РФ, external, read-only)
        ↓
Knowledge Base (curated: physician-reviewed diagnosis + regimen layers)
        ↓
Clinical Decision Engine (10-stage pipeline + safety gates + curated gate)
        ↓
REST API  ← the single public contract
        ↓
 ┌────────┬────────┬────────┬─────────┬──────┐
 │  HTML  │  Web   │ Mobile │ Desktop │ CLI  │
 └────────┴────────┴────────┴─────────┴──────┘
```

КР changes are reflected in exactly one place (knowledge base + engine); every interface
consumes the same medical logic. No client holds independent medical logic or its own
antibiotic database.

### Approved adjustments incorporated
1. **The API remains the single public contract.** All clients consume the same HTTP API.
2. **`REVIEW_REQUIRED` is an application status carried over HTTP 200**, never an HTTP error.
3. **The main recommendation response is self-contained** for routine clinical use: it includes
   the primary recommendation, dose, duration, alternatives, and contraindications in one
   response. Clients make **no** additional request for primary clinical information. Separate
   endpoints may exist for *extended* provenance or document exploration only.

### Reconciling "self-contained" with "no duplicated medical knowledge"
- **No duplication _at rest_:** the curated artifacts and the repository store only identifiers,
  approvals, and provenance. The upstream corpus (`C:\clinrec_downloader`, read-only) remains the
  single system of record for all clinical content.
- **Content _in the response_:** clinical fields (drug, dose, route, frequency, duration,
  therapy line, safety) are read **live** by the engine from `normalized_regimens.sqlite` during
  a request and serialized into a transient response. The response is a **projection**, not a
  stored copy. Nothing medical is persisted in the API tier or any client.

---

## 1. Public API contract (single boundary)

Transport-agnostic operation; HTTP/JSON is the binding all clients use.

### `POST /v1/recommend`

**Request:**
```json
{
  "api_version": "1",
  "query": {
    "diagnosis": "string|null",
    "icd10": "string|null",
    "patient": {
      "age": 0, "weight_kg": 0, "pregnant": false,
      "renal_function": "string|null", "hepatic_impairment": false,
      "allergies": ["string"], "current_meds": ["string"]
    },
    "preferences": {
      "therapy_line": "string|null", "route_preference": "string|null",
      "population": "adult|child|null"
    }
  }
}
```
Mirrors the existing `PatientQuery` / `Patient` / `Preferences`. No new clinical inputs.

**Response — self-contained (routine clinical use):**
```json
{
  "api_version": "1",
  "status": "APPROVED | REVIEW_REQUIRED | ERROR",
  "knowledge_version": "curated-YYYY-MM-DD",
  "diagnosis": {
    "input": "острый гайморит",
    "resolved_guideline_ids": ["1220"],
    "routing_confidence": "HIGH|MEDIUM|LOW|NONE",
    "trace": "Diagnosis Resolution … (why this guideline; alternatives lost)"
  },
  "recommendations": [
    {
      "rank": 1,
      "therapy_line": "first_line | alternative",
      "regimen_id": "5351",
      "guideline_id": "343",
      "drug": { "normalized": "Амоксициллин", "atc_code": "J01CA04|null" },
      "dose": {
        "value": 500, "unit": "мг", "route": "внутрь",
        "frequency_per_day": 3,
        "duration": { "min_days": 5, "max_days": 7, "text": "5–7 дней" },
        "calculated_dose_mg": 1500
      },
      "safety": {
        "contraindications": [
          { "code": "PREGNANCY_CI|AGE_BELOW_MIN|ALLERGY|CI_UNPARSED",
            "level": "ABSOLUTE|WARNING", "message": "…" }
        ],
        "flags": [ { "code": "RENAL_ADJ_UNPARSED", "level": "WARNING", "message": "…" } ]
      },
      "provenance": {
        "kr_code": "494", "guideline_id": "343", "regimen_id": "5351",
        "guideline_year": 2024, "page_number": "27",
        "pdf_sha256": "3210…", "pdf_sha256_verified": true
      },
      "review": { "decided_by": "…", "decided_at": "…", "review_status": "APPROVED" }
    }
  ],
  "excluded": [
    { "regimen_id": "…", "drug": "Доксициклин", "reason": "allergy: Тетрациклины" }
  ],
  "review": { "code": "…", "reason": "…" },
  "errors": [ { "code": "…", "category": "…", "detail": "…" } ],
  "notes":  [ { "code": "…", "severity": "INFO|WARN", "message": "…" } ]
}
```

**Contract invariants:**
- The API always wraps `CuratedEngine`; the raw `Engine` is never exposed. Clients cannot obtain
  unapproved output.
- `recommendations` is non-empty **only** when `status == "APPROVED"`.
- First-line vs. alternative is expressed by `therapy_line`; `recommendations` is rank-ordered,
  so "alternatives" are simply the lower-ranked approved entries — all in the one response.
- Every recommendation carries full provenance and physician attribution.
- Every recommendation's clinical content is read live from upstream (not stored).

### Extended (optional) endpoints — never required for routine use
- `GET /v1/provenance/{regimen_id}` — full chain incl. `source_quote`, section, PDF reference
  (INT-2 resolver, read-only).
- `GET /v1/document/{guideline_id}` — source document metadata / page pointers for exploration/audit.
- `GET /v1/health` — corpus + curated-knowledge readiness.

These add depth (full source text, audit) but are not needed to prescribe routinely.

---

## 2. Versioning strategy (three independent axes)

| Axis | Field | Changes when | Rule |
|---|---|---|---|
| API contract | `api_version` (major) | request/response shape changes | additive within a major; breaking → `/v2`, old major kept during a deprecation window |
| Curated knowledge | `knowledge_version` | physician re-curates / regenerates `curated_knowledge.json` | monotonic; clients may pin or read latest |
| Source guideline | per-item `kr_code` + `guideline_year` + `pdf_sha256` | a КР PDF is replaced upstream | `pdf_sha256` change invalidates that regimen's approval (INT-3 binding) → it drops to REVIEW_REQUIRED until re-reviewed |

Guideline evolution flows through `knowledge_version` and per-item `pdf_sha256` and **never breaks
the API contract**. Clients pin only `api_version` (major).

---

## 3. REVIEW_REQUIRED behaviour (never silently degrade)

- First-class application status: `status: "REVIEW_REQUIRED"`, `recommendations: []`, populated
  `review { code, reason }`.
- **HTTP 200** (a valid clinical-safety outcome, not a transport error). Clients MUST branch on
  `status`, not on HTTP code.
- Sourced from the INT-4 `CuratedEngine` / `ReviewRequired` gate.
- **Client contract:** REVIEW_REQUIRED renders as a distinct, non-actionable
  "требует врачебной проверки" state. Falling back to any local, cached, or embedded
  recommendation is a contract violation. The API cannot emit an unapproved recommendation, so the
  only way a client can display one is by violating the contract.

---

## 4. Error taxonomy (machine-readable; reuses existing codes)

Each error: `{ code, category, detail }`. Codes are stable within a major `api_version`
(never renamed; new ones may be added).

| Category | code(s) | Origin | HTTP |
|---|---|---|---|
| review required | `NO_APPROVED_DIAGNOSIS`, `NO_APPROVED_REGIMEN`, `KNOWLEDGE_UNAVAILABLE` | INT-4 gate | 200 (`status:REVIEW_REQUIRED`) |
| missing diagnosis | `DIAGNOSIS_NOT_FOUND`, `NO_APPROVED_DIAGNOSIS` | DiagnosisMatch / curated | 200 / 422 |
| missing regimen | `REGIMEN_NOT_FOUND`, `NO_REGIMENS_EXTRACTED`, `MISSING_REGIMEN` | INT-2 / INT-3 | 422 |
| provenance failure | `METADATA_NOT_FOUND`, `PDF_NOT_FOUND`, `SHA_MISMATCH`, `REVIEW_INFO_MISSING`, `PROVENANCE_CHAIN_BROKEN` | INT-2 / INT-4 | 422 / 409 |
| corpus unavailable | `CORPUS_UNAVAILABLE` | INT-1 `CorpusUnavailableError` | 503 |
| validation failure | `DUPLICATE_DECISION`, `ORPHAN_REVIEW`, `ORPHAN_CURATED_ENTRY`, `APPROVED_DIAGNOSIS_MISSING_REGIMEN`, `APPROVED_REGIMEN_MISSING_DIAGNOSIS`, `PHYSICIAN_APPROVAL_MISSING` | INT-3 / INT-4 validators | 500 (deploy-time) |

---

## 5. Client responsibilities (strict three-layer separation)

| Layer | Owns | Must NOT |
|---|---|---|
| Clinical Decision Engine (`clinical_engine`, unchanged) | pipeline, safety gates, determinism, curated gate, provenance, live content read | expose transport; know about clients |
| API (new, INT-5) | contract, versioning, serialization, auth, rate-limit, health; wraps `CuratedEngine`; assembles the self-contained response; serves extended provenance read-only | contain any clinical logic, thresholds, drug data, or fallback |
| Presentation (HTML, Web, Mobile, Desktop, CLI) | input capture, rendering the response, showing provenance + REVIEW_REQUIRED | contain any medical logic or independent antibiotic DB; cache/derive/compute recommendations |

**Hard rule:** the HTML calculator's embedded `db/diseases/*` + antibiotic DB is removed when it is
migrated to the API. All names/doses/durations/contraindications/alternatives come from the API.
A presentation layer that computes anything clinical violates the contract.

---

## 6. Backward compatibility

- **Engine level:** curated mode stays the opt-in `CuratedEngine` wrapper; the raw `Engine` and all
  existing internal behaviour/tests are unchanged.
- **API level:** the public API is new — no existing external integrations to break. It is
  curated-only by definition.
- **Calculator migration:** the current calculator keeps working on its embedded DB until it is
  switched to the API; the switch is a one-way cutover (embedded medical DB removed then). No dual
  source of truth coexists in production.
- **Contract compatibility:** additive-only within `api_version:"1"`; consumers ignore unknown
  fields; breaking changes ⇒ `/v2` with an overlap window.

---

## 7. Deployment strategy (external read-only corpus in production)

- Corpus location resolved by INT-1: **`ANTIBIO_CORPUS_DIR` (prod env) overrides** the committed
  `corpus_config.json` default. In production the env var points at a **read-only mount** of the
  corpus.
- The corpus is never baked into the image or git; it is mounted read-only. INT-1's
  `mode=ro&immutable=1` guarantees no writes/sidecars regardless of mount permissions.
- **Startup / health check:** the API verifies `CorpusLocator.available()`; if not, it serves
  `503 CORPUS_UNAVAILABLE` and refuses `recommend` — never degrades to unapproved output.
- **Curated artifacts** (`curated_knowledge.json`, `diagnosis_index.curated.json`,
  `curated_regimens.json`) are generated at build/deploy time from the physician ledgers, validated
  by the INT-3/INT-4 validators (deploy fails if `INVALID`), and shipped as read-only artifacts.
  `knowledge_version` is stamped from them.
- **Extended provenance/content** is streamed live from the corpus mount via the INT-2 resolver;
  no medical text is persisted in the API tier.

---

## 8. Readiness verdict & next step

The internal mechanisms (read-only corpus, provenance, physician-gated curation, unified curated
layer, review-required semantics, live clinical content on each candidate) are in place and tested.
The contract above is expressible from existing symbols with **no engine / routing / safety change**.

**Ready to proceed to INT-5 implementation upon approval of this document.**

Proposed INT-5 increments (each additive, stop-for-review):
- **INT-5a** — API service skeleton: `POST /v1/recommend` wrapping `CuratedEngine`, self-contained
  response serializer, `status`/error taxonomy, `/v1/health`. No client changes.
- **INT-5b** — extended endpoints (`/v1/provenance/{regimen_id}`, `/v1/document/{guideline_id}`).
- **INT-5c** — migrate the HTML calculator to a pure presentation client; remove its embedded
  medical DB.

No implementation until this document is approved.
