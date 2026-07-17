# RC-030 C3 — Classification Matrix (Phase 2)

Every untracked candidate from `RC030_C3_WORKTREE_INVENTORY.md` classified individually. Categories per governing instructions:

A. governed source documentation B. governed tooling C. small reproducibility manifest D. generated evidence — exclude E. local review artifact — exclude F. temporary artifact — delete/ignore G. historical unrelated artifact — leave untouched H. owner decision required

## INCLUDED — C3-DOCS (39 governed reports, category A)

All are pure Markdown, derived analysis/decisions (no full clinical-row dumps), content-audited in Phase 3 for false/stale claims, no secrets, no personal paths introduced. Size and SHA-256 recorded; full detail in `RC030_C3_EXACT_ALLOWLIST.md`.

| # | Path | Size | Purpose | Derived? | Clinical quotes? | Decision |
|---|---|---|---|---|---|---|
| 1 | RC030_FULL_REPAIR_BASELINE.md | 1350 B | Baseline snapshot before full repair | Yes | No | INCLUDE |
| 2 | RC030_FULL_REPAIR_IMPLEMENTATION_REPORT.md | 3833 B | What changed and why (corrected in Phase 3) | Yes | No | INCLUDE |
| 3 | RC030_FULL_REPAIR_PILOT_REPLAY_REPORT.md | 3158 B | Replay methodology summary | Yes | No | INCLUDE |
| 4 | RC030_FULL_REPAIR_CORPUS_IMPACT.md | 1365 B | Corpus-wide impact summary | Yes | No | INCLUDE |
| 5 | RC030_FULL_REPAIR_IMPACT_MATRIX.md | 1429 B | Impact matrix | Yes | No | INCLUDE |
| 6 | RC030_FULL_REPAIR_PRESTAGING_AUDIT.md | 3117 B | Prior prestaging audit (this program) | Yes | No | INCLUDE |
| 7 | RC030_DEFECT_CLUSTER_REGRESSION_REPORT.md | 2567 B | Defect clustering + regression coverage | Yes | No | INCLUDE |
| 8 | RC030_RANGE_REBUILD_INTEGRITY_REPORT.md | 3402 B | Non-authoritative experimental rebuild integrity; states 179/365 SUSPECT | Yes | Short excerpts only (e.g. "0,6-0,9 г") | INCLUDE |
| 9 | RC030_MAXIMUM_RANGE_DISAMBIGUATION_REPORT.md | 2482 B | Max-dose vs range disambiguation, all BLOCKED | Yes | No (regimen IDs + category only) | INCLUDE |
| 10 | RC030_AUTHORITATIVE_RANGE_MIGRATION_PROPOSAL.md | 1829 B | Design-only migration proposal, not executed | Yes | No | INCLUDE |
| 11 | RC030_ADDITIVE_RANGE_SCHEMA_PROPOSAL.md | 3846 B | Schema proposal | Yes | No | INCLUDE |
| 12 | RC030_DOSE_SEMANTICS_ARCHITECTURE_DECISION.md | 4922 B | Architecture decision record | Yes | No | INCLUDE |
| 13 | RC030_RANGE_EXPRESSION_RCA.md | 4746 B | Root-cause analysis of range collapse | Yes | Short excerpts | INCLUDE |
| 14 | RC030_RANGE_LOSS_STAGE_RCA.md | 4243 B | RCA of which pipeline stage loses ranges | Yes | Short excerpts | INCLUDE |
| 15 | RC030_VERDICT_TAXONOMY_DECISION.md | 3686 B | Verdict taxonomy decision | Yes | No | INCLUDE |
| 16 | RC030_SOURCE_VALIDATION_BASELINE.md | 2400 B | Source validation baseline | Yes | No | INCLUDE |
| 17 | RC030_TARGETED_RECOVERY_BASELINE.md | 2340 B | Recovery baseline (references `C:\clinrec_downloader\` as a documented local source-storage root, retained — see note below) | Yes | No | INCLUDE |
| 18 | RC030_VALIDATION_SAMPLE_DESIGN.md | 2961 B | Sample design methodology | Yes | No | INCLUDE |
| 19 | RC030_TABLE_CLIPPED_TEXT_RECOVERY_REPORT.md | 4153 B | Table-clipping recovery findings | Yes | Short excerpts | INCLUDE |
| 20 | RC030_CYRILLIC_TABLE_TEXT_COMPARISON.md | 3296 B | OCR Cyrillic-corruption comparison | Yes | Short excerpts | INCLUDE |
| 21 | RC030_PDF_COVERAGE_GAP_REPORT.md | 2498 B | PDF coverage gap correction (references `C:\clinrec_downloader\`) | Yes | No | INCLUDE |
| 22 | RC030_FORMULATION_AVAILABILITY_REPORT.md | 2430 B | Formulation availability audit | Yes | No | INCLUDE |
| 23 | FORMULATION_DATA_GAP_REPORT.md | 2928 B | Formulation data gap audit | Yes | No | INCLUDE |
| 24 | RC030_SIX_TOOL_AVAILABILITY_AUDIT.md | 3199 B | Extraction-tool availability audit | Yes | No | INCLUDE |
| 25 | RC030_SIX_TOOL_REAL_EXECUTION_AUDIT.md | 4615 B | Extraction-tool real-execution audit | Yes | No | INCLUDE |
| 26 | RC030_TEST_PORTABILITY_POSTCOMMIT_REPORT.md | 3682 B | Portable-test verification | Yes | No | INCLUDE |
| 27 | RC030_TARGETED_RECOVERY_AND_OWNER_PILOT_REPORT.md | 9907 B | Combined recovery + pilot narrative (references `C:\clinrec_downloader\`) | Yes | Short excerpts | INCLUDE |
| 28 | RC030_AI_AUDIT_DOUBLE_PASS_REPORT.md | 922 B | AI audit methodology summary (not human validation) | Yes | No | INCLUDE |
| 29 | RC030_AI_PRE_REVIEW_REPORT.md | 6270 B | AI pre-review summary | Yes | No | INCLUDE |
| 30 | RC030_AI_PRE_REVIEW_DISAGREEMENTS.md | 9265 B | AI disagreement analysis | Yes | No | INCLUDE |
| 31 | RC030_AUTONOMOUS_AI_AUDIT_REPORT.md | 3235 B | Autonomous AI audit report | Yes | No | INCLUDE |
| 32 | RC030_AUTONOMOUS_AI_AUDIT_DISAGREEMENTS.md | 4244 B | Autonomous AI disagreements | Yes | No | INCLUDE |
| 33 | RC030_AUTONOMOUS_AI_DEFECT_CLUSTERS.md | 5781 B | AI-found defect clusters | Yes | No | INCLUDE |
| 34 | RC030_AUTONOMOUS_AI_EXPLORATORY_METRICS.md | 1548 B | Exploratory metrics | Yes | No | INCLUDE |
| 35 | RC030_AUTONOMOUS_AI_FIX_PLAN.md | 3545 B | AI-suggested fix plan (not authorized/executed) | Yes | No | INCLUDE |
| 36 | RC030_AUTONOMOUS_AI_RANGE_IMPACT.md | 1307 B | AI range-impact summary | Yes | No | INCLUDE |
| 37 | RC030_AUTONOMOUS_AI_TABLE_AUDIT.md | 3519 B | AI table audit | Yes | No | INCLUDE |
| 38 | RC030_AUTONOMOUS_AI_THREE_WAY_COMPARISON.md | 6344 B | Three-way comparison (parser/sandbox/AI) | Yes | No | INCLUDE |
| 39 | RC030_FULL_AI_AUDIT_BASELINE.md | 1453 B | AI audit baseline | Yes | No | INCLUDE |

**Note on `C:\clinrec_downloader\` references (items 17, 21, 27):** this is a documented local source-PDF storage root, not a personal path (no username, no home directory) — it is factual RCA content describing which storage locations were searched. Redacting it would alter the historical meaning of the RCA per the governing instruction "do not alter the historical meaning of reports merely to make them look cleaner." Retained as-is; flagged here for owner visibility.

**Note on AI-audit reports (28–39):** scanned for `human validation|approved by human|manually validated|reviewer approved|clinician approved` — zero matches. All correctly frame AI findings as pre-review/audit input, not clinical or human approval. Consistent with the required canonical statement "AI audit is not human validation."

## INCLUDED — C3-MANIFEST (category C, compact)

| Path | Size | Content | Decision |
|---|---|---|---|
| RC030_FULL_REPAIR_BASELINE.json | 1136 B | Counts + DB/code hashes only, no row payload | INCLUDE |
| RC030_FULL_REPAIR_CORPUS_IMPACT.json | 1015 B | Aggregate distributions only, no row payload | INCLUDE |
| RC030_RANGE_REPROCESS_MANIFEST_SUMMARY.json | 5332 B (new, Phase 5) | Compact summary of the 304 KB full manifest — schema_version, hashes, counts, defect_categories, affected_regimen_ids (365 IDs, no quotes/offsets) | INCLUDE |

## INCLUDED — C3-TOOLS

None. See `RC030_C3_PRESTAGING_AUDIT.md` Phase 6/9 — no deterministic replay/rebuild script exists as a standalone committable file; all range-rebuild/recovery execution happened via `generated/rc030_recovery/build_interface.py` and `build_control_sample_interface.py`, which live entirely inside the excluded `generated/` scratch tree (HTML-generation utilities for the owner review UI, not deterministic data tooling) and are not included in C3.

## INCLUDED — C3-TESTS

None. No test exists that exercises only the C3 documentation/manifest content (nothing executable is being added).

## EXCLUDED (category D — generated evidence)

| Path | Size | Reason |
|---|---|---|
| RC030_RANGE_REPROCESS_MANIFEST.json | 304 KB | 365-row payload incl. source offsets, raw range text, drug names — replaced by compact summary above |
| CORPUS_MANIFEST.json | 210 KB | Full PDF/regimen corpus manifest |
| RC030_RANGE_REBUILD_DIFF.json | 109 KB | Row-level diff dump |
| RC030_AUTONOMOUS_AI_AUDIT_EVENTS.json | 93 KB | AI audit raw event store |
| RC030_AI_PRE_REVIEW_EVENTS.json | 75 KB | AI pre-review raw event store |
| REPOSITORY_UNTRACKED_INVENTORY.json | 68 KB | Stale full inventory dump, superseded by this matrix |
| RC030_MISSING_PDF_MANIFEST.json | 61 KB | 193 per-PDF records incl. Russian clinical-topic filenames |
| RC030_VALIDATION_SAMPLE_MANIFEST.json | 51 KB | Per-row sample-selection manifest |
| RC030_AI_AUDIT_PASS1.json | 33 KB | AI audit raw event store |
| RC030_AI_AUDIT_PASS2.json | 21 KB | AI audit raw event store |
| RC030_FULL_REPAIR_PILOT_REPLAY.json | 21 KB | Full replay dataset (explicitly listed for exclusion) |
| RC030_MAXIMUM_RANGE_DISAMBIGUATION.json | 15 KB | Full machine-readable disambiguation dump (explicitly listed for exclusion) |
| RC030_MAX_DOSE_OWNER_QUEUE.json | 15 KB | Owner review queue export |
| RC030_AI_OWNER_CONTROL_SAMPLE.json | 13 KB | AI/owner control-sample export |
| RC030_TARGET_PAGE_MANIFEST.json | 10 KB | Page-targeting manifest |
| RC030_OWNER_PILOT_QUEUE.json | 5 KB | Owner review queue export |
| medical_dictionary/unknown_drugs.csv | 83 KB | Generated dictionary-gap data |
| `generated/` (whole tree) | 34 MB | PDFs, page crops, MinerU/Docling/RapidTable/DocLayout-YOLO raw outputs, owner-review HTML, 1 SQLite |
| `dose_verification_sandbox/data/` | 15 MB | Already gitignored (`.gitignore` lines 95-97) |

## EXCLUDED (category E — local review artifact)

| Path | Size | Reason |
|---|---|---|
| `pilot_review_batch/*.json` (26 files) | up to 26 KB each | Per-task owner review exports |
| `pilot_review_batch_v2/*.json` (23 files) | up to 26 KB each | Per-task owner review exports (v2) |
| `dose_verification_sandbox/owner_fidelity_event_schema.json` | 2554 B | Schema *for* owner event stores — kept with its source module (see category H below), not split out |

## EXCLUDED (category F — temporary/stale artifact)

None found requiring deletion; the one stale artifact (`RECOVERY_TRACKED_FILES.txt`) is classified under G instead since it documents a real historical event rather than being disposable scratch.

## EXCLUDED (category G — historical unrelated artifact, leave untouched)

| Path | Size | Reason |
|---|---|---|
| RECOVERY_TRACKED_FILES.txt | 16 KB | `git status`-style dump referencing a pre-refactor repo layout (`antibiotic_calc.html`, `db/`, `.env.example`) unrelated to `medical_normalizer`/`clinical_engine`/RC-030. Real historical artifact from a prior incident; not RC-030 C3 material. Left untouched, not staged. |
| SESSION_HISTORY.md | 115 KB | Raw session transcript (Russian, casual dev notes, local-server troubleshooting). Not RC-030 governance documentation; falls under "large raw chat transcripts" which project memory conventions explicitly exclude from persistent storage. Not staged. |
| SESSION_SUMMARY.md | 3.9 KB | Executive project handoff doc — general P5.6 status, not RC-030-specific; duplicates the AI_LOG/PROJECT_STATE handoff convention already in place. Not staged. |
| P56_GOVERNANCE_HARDENING_CLOSURE_REPORT.md, `_FRESH_CLONE_REPORT.md`, `_STAGED_AUDIT.md` | 8.2/4.3/3.1 KB | Different governance stream (P5.6 sandbox hardening, already self-titled "CLOSURE"), unrelated to RC-030 full repair. Left for its own commit if ever needed. |
| RC030_OWNER_PILOT_GUIDE.md, RC030_OWNER_PILOT_CONSOLIDATION_REPORT.md, RC030_OWNER_PILOT_CONSOLIDATION_BASELINE.md, RC030_MAX_DOSE_OWNER_GUIDE.md | 3.6/8.8/1.7/2.6 KB | Operating guides for the owner-review HTML workflow, whose interface (`generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html`) is itself excluded (category D). Committing the guide without the tool it documents would be orphaned/misleading documentation. Reclassified from initial A to H below — owner decision required on whether to commit the HTML tool first. |
| RC030_COMMIT_B_BASELINE.md, `_POSTCOMMIT_VERIFICATION.md`, `_PRESTAGING_AUDIT.md` | 5.2/3.4/4.3 KB | Meta-reports about the C2 ("Commit B") staging process itself, already superseded by the formal C2 fresh-clone verification recorded in this session's transcript. Redundant with committed history; not RC-030 repair documentation proper. Not staged. |

## EXCLUDED (category H — owner decision required)

| Path | Size | Reason |
|---|---|---|
| dose_verification_sandbox/precision_calculator.py | 4198 B | New sandbox calculation-adjacent module, self-classified by `RC030_FULL_REPAIR_IMPLEMENTATION_REPORT.md` as "unrelated to this repair." Committing calculation logic is outside C3's docs/tooling purpose and outside this session's authorization. |
| dose_verification_sandbox/validation_unit.py | 3607 B | Same as above |
| dose_verification_sandbox/verdict_taxonomy.py | 3676 B | Same as above |
| dose_verification_sandbox/owner_fidelity_events.py | 3936 B | Same as above; owner-event-store logic |
| dose_verification_sandbox/owner_fidelity_event_schema.json | 2554 B | Schema for the above; committed only together with its module, deferred with it |
| tests/dose_verification_sandbox/test_owner_pilot_consolidation.py | 6667 B | Tests the above; deferred with it |
| tests/dose_verification_sandbox/test_targeted_recovery_pilot.py | 5472 B | Tests the above; deferred with it |
| RC030_OWNER_PILOT_GUIDE.md, RC030_OWNER_PILOT_CONSOLIDATION_REPORT.md, RC030_OWNER_PILOT_CONSOLIDATION_BASELINE.md, RC030_MAX_DOSE_OWNER_GUIDE.md | see above | Orphaned without their referenced tool; owner should decide whether to commit the owner-review HTML interface (currently in `generated/`, excluded) in a future dedicated commit, then re-evaluate these guides together with it |

## Summary counts

- INCLUDE (C3-DOCS): 39
- INCLUDE (C3-MANIFEST): 3
- INCLUDE (C3-TOOLS): 0
- INCLUDE (C3-TESTS): 0
- EXCLUDE (D): 19 individual files + 2 large directories
- EXCLUDE (E): 49 files + 1 schema (deferred with H)
- EXCLUDE (G): 12 files
- EXCLUDE (H): 7 files + 4 files cross-listed from G
