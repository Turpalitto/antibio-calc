# RC031_EVIDENCE_INTEGRITY_HARDENING_REPORT.md

Date: 2026-07-16
Scope: False Clinical Finding Retraction and Evidence-Integrity Hardening

## Summary

| Phase | Output | Status |
|---|---|---|
| 0 | `RC031_RETRACTION_AUDIT.md` | Done — full repo search, every occurrence classified A–F, zero stale false claims found, one corrupted (mojibake) generated artifact found and deleted |
| 1 | `evidence/generate_regimen_5574_evidence.py`, `evidence/regimen_5574_verified_evidence.json`, `REGIMEN_5574_VERIFICATION_REPORT.md` | Done — machine-generated from live, read-only queries + PyMuPDF extraction; report rendered from the JSON packet, not hand-typed |
| 2 | `dose_verification_sandbox/evidence_model.py` — `EvidenceBlock` | Done — 6 allowed origins, machine origins require `source_hash`+`retrieval_command`, reject hand-written content at construction |
| 3 | `render_markdown()` / `verify_packet()` | Done — fails closed on missing/tampered evidence, re-derives `packet_hash` before rendering |
| 4 | `tests/dose_verification_sandbox/test_evidence_integrity.py` | Done — 14 tests, all pass |
| 5 | `ROOT_CAUSE_REGISTER.md` RC-031 | Done — structured `status`/`classification`/`root cause`/`clinical corpus impact`/`derived-document impact`/`preventive action` fields |
| 6 | Handoff consistency | Done — all 10 named files carry the required statements, verified by grep |
| 7 | Commit split reconfirmation | Done — final, complete file lists for Commit A/B in `DOSE_SANDBOX_PRECOMMIT_AUDIT.md`, required labels specified, nothing staged |
| 8 | Final regression | 96/96 sandbox tests pass; source DB hashes unchanged; approved=0; canonical pytest running (see below) |

## Regimen 5574 — machine-verified, final state

```
antibiotic: джозамицин            (assembled_regimens.sqlite, live query)
drug_normalized: джозамицин       (normalized_regimens.sqlite, live query)
source PDF page 16: "джозамицин** 50 мг на кг массы тела в сутки..."  (PyMuPDF extraction)
drug_name_consistent: true         (GENERATED_CALCULATION cross-check)
dose_consistent: true              (50 mg/kg, both layers)
```

Packet hash: see `evidence/regimen_5574_verified_evidence.json` (`packet_hash` field) — any future
tampering or re-query producing a different result is mechanically detectable via
`evidence_model.verify_packet()`.

## What the evidence-integrity hardening actually prevents

The RC-031 false finding happened because a piece of hand-written prose ("Азитромицин\*\* 50 мг на кг
массы тела в сутки...") was presented in a report as if it were a verbatim database quote. The new
`EvidenceBlock` contract makes this specific failure mode a **runtime error, not a review-catchable
mistake**: constructing an `EvidenceBlock` with `evidence_origin="DATABASE_QUERY"` or
`"SOURCE_PDF_EXTRACT"` and no `source_hash`/`retrieval_command` raises `EvidenceIntegrityError`
immediately, before the content can ever reach a rendered report. `HUMAN_NOTE`/`PARAPHRASE` blocks are
still allowed (commentary is legitimate) but can never claim `is_exact=True`, so a rendered report
visually distinguishes `[DATABASE QUERY — verified ...]` from `[COMMENTARY — human note, not verified
evidence]`.

## Commit status

**Nothing staged or committed.** Two-commit plan finalized in `DOSE_SANDBOX_PRECOMMIT_AUDIT.md` with
exact, complete file lists for both Commit A (base sandbox, zero RC-030 content) and Commit B (all
RC-030 + evidence-integrity work, labeled `UNVALIDATED`/`CALCULATION_BLOCKED`/`NOT CLINICALLY
APPROVED`). Awaiting an explicit owner approval command for either commit.

## Safety invariants (reconfirmed)

- `assembled_regimens.sqlite`, `kb_p44.db`, `kb_final.db`, `review_workbench_p56.sqlite` SHA-256
  hashes byte-identical to the original Phase 0 baseline (`RC030_VALIDATION_BASELINE.md`).
- `assembled_regimens` rows with `status='APPROVED'`: 0.
- No `clinical_engine` import anywhere in `dose_verification_sandbox/` or `evidence/`.
- 96/96 sandbox tests pass (was 83 before this pass; 13 new: 1 removed-corrupted-artifact-adjacent
  cleanup + 14 evidence-integrity tests, net +13 after accounting for file reorganization).
- No source database or PDF file copied into the repository; `evidence/regimen_5574_verified_evidence.json`
  contains only hashes and extracted text, never the source files themselves.

## Final verdict

**A) RETRACTION COMPLETE — SANDBOX COMMIT A READY FOR OWNER APPROVAL**

RC-031 is fully retracted with a machine-verifiable evidence packet proving regimen 5574 was correct
all along. No stale false claim remains anywhere in the repository (Phase 0 audit, zero findings).
Evidence-integrity tooling is built, tested, and structurally prevents a repeat of this specific
failure mode. Commit A (the base P5.6 sandbox) has no RC-030 or RC-031 content, works standalone,
fails closed without the semantics layer, and its allowlist is finalized — it is ready for an owner
approval command whenever the owner chooses to give one. Commit B (RC-030 experimental semantics +
evidence-integrity hardening) remains correctly labeled `UNVALIDATED`/`CALCULATION_BLOCKED`/`NOT
CLINICALLY APPROVED` and is not proposed for staging in this pass.

**P6 remains BLOCKED.**
