# RC-030 Targeted Recovery — Baseline

Recorded 2026-07-16, before any Phase 1+ work.

- HEAD: `394818675b0ed199e03cae1d89e38a488f5102ce` (`3948186`, `test(rc030): make database invariants portable in bare clones`)
- `git status`: nothing staged; Part III artifacts from the prior turn remain untracked (`RC030_TEST_PORTABILITY_POSTCOMMIT_REPORT.md`, `dose_verification_sandbox/validation_unit.py`, `RC030_SOURCE_VALIDATION_BASELINE.md`, `RC030_SIX_TOOL_AVAILABILITY_AUDIT.md`, `RC030_FORMULATION_AVAILABILITY_REPORT.md`, `RC030_DOSE_SEMANTICS_ARCHITECTURE_DECISION.md`, `RC030_VALIDATION_SAMPLE_DESIGN.md`, `RC030_VALIDATION_SAMPLE_MANIFEST.json`), plus older untracked P5.6/RC-030 audit reports and generated-artifact directories from earlier turns (`pilot_review_batch*`, `dose_verification_sandbox/data/`, `CORPUS_MANIFEST.json`, etc.) — unchanged, not touched this turn.
- Source DB hashes: `assembled_regimens.sqlite` = `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9`; `normalized_regimens.sqlite` = `c7b67354b0723ad538a185e561ed94d09b11c019279be9c4c6412c4f1eaa4237` — unchanged.
- PDF corpus location: `C:\clinrec_downloader\downloads_active\` (external to the repo, per `CORPUS_MANIFEST.json`'s `source_root`) — **477 PDFs present locally**, confirmed to include the regimen-5574 source (`Урогенитальные заболевания, вызванные Mycoplasma genitalium.pdf`).
- Generated-artifact directories: `dose_verification_sandbox/data/` (existing, gitignored-by-convention/untracked), no `generated/rc030_recovery/` yet — will be created fresh, gitignored.
- Disk space: 115 GB free of 952 GB on `C:`.
- Python interpreter: 3.12.10.
- GPU availability: **none** — `torch==2.4.1+cpu`, `torch.cuda.is_available() == False`. All extraction/layout work in this turn runs CPU-only.
- Approved-object count: 0 (`review_decisions` = 0 rows).
- Review database state: unchanged from all prior turns (9,153 tasks, all `PENDING`).
- Active calculation-eligibility count: **0 / 2,675** (live re-derivation via `classify_regimen` → `assess_risk` → `validate`).

## Required baseline check

- Active QA-calculable count = 0 — ✅
- Clinically approved count = 0 — ✅
- Clinical Engine disconnected — ✅ (unchanged from prior turns, re-confirmed by the same `grep` used previously)
