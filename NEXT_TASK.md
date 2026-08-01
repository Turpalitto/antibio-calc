# NEXT_TASK.md — ANTIBIO

## Immediate owner input for physician pilot — 2026-08-01

Read-only pilot preflight is green; no reviewer registry exists. Before any
review task can be assigned, the owner must provide real data for four
people: Reviewer A, independent Reviewer B, Adjudicator, and Medical QA Lead.

Required per person: stable `reviewer_id`, display name, professional role,
organisation, and assigned review role. Optional: credential reference and
credential expiry. Also provide `registered_by` for the registration audit
trail. Do not send credential documents or other sensitive personal data.

After receipt: create the local gitignored registry through
`ReviewerRegistry.register(...)`, verify `pilot_status`, launch the local
Review Workbench, and assign only the governed 30-task pilot. Do not connect
Clinical Engine or change clinical approval state automatically.

## Next task after publication — 2026-08-01

The validated P5.6/C7 commits through `bab018f` are published on
`origin/main`. Do not repeat repository publication, C7 source-fidelity
review, or fresh-clone verification.

Next owner-governed actions:

1. provide and register real Reviewer A identity and professional metadata;
2. provide and register independent Reviewer B;
3. provide and register Adjudicator and Medical QA Lead;
4. assign the governed physician pilot with blinding and audit history;
5. keep every regimen non-approved and calculation-blocked until the complete
   review/consensus/Medical-QA state machine succeeds.

Do not invent reviewer identities. Do not connect Clinical Engine. P6 still
requires physician-approved objects, approved-data Golden, shadow validation,
safety gates, request-audit snapshot, and explicit owner authorization.

## Next task after fresh-clone PASS — 2026-07-30

Fresh-clone/lock/tests are complete. Do not repeat C7 source-fidelity review
and do not connect Clinical Engine.

Next repository action: push the validated commits only when explicitly
authorized.

Next clinical-governance action after publication:

1. register real Reviewer A;
2. register real Reviewer B;
3. register Adjudicator and Medical QA Lead;
4. assign the governed physician pilot;
5. preserve blinding, independence, provenance, and audit history;
6. keep all regimens non-approved and calculation-blocked until the full
   review/consensus/Medical-QA state machine completes.

P6 still additionally requires approved-data Golden, shadow validation,
safety gates, request-audit snapshot, and explicit owner authorization.

## Next task after commit 60e6033 — 2026-07-30

The exact C7 acceptance boundary is committed. Do not repeat C7 owner review
and do not connect Clinical Engine.

Next:

1. install/use `uv` in an isolated clone;
2. run `uv lock --check`;
3. run frozen test dependency sync;
4. verify collection and full canonical suite at commit `60e6033`;
5. publish the accepted commits when explicitly authorized;
6. only then proceed to real reviewer registration and physician pilot.

P6 entry still requires real physician reviews, physician-approved objects,
approved-data Golden pass, shadow/safety gates, request audit snapshot, and
explicit owner authorization. C7 source-fidelity events cannot satisfy these
clinical gates.

## Next task after P5.6 C7 acceptance audit — 2026-07-30

Use only `P56_C7_ACCEPTANCE_PROPOSED_ALLOWLIST.txt` for the next commit
boundary. Do not use `git add .`.

Required sequence:

1. review the exact 94-file allowlist;
2. stage only those files;
3. scan the staged index for secret patterns and forbidden DB/PDF/key/env
   artifacts;
4. verify staged diff and file count;
5. create a new commit (do not amend historical commits);
6. run `uv lock --check`, frozen dependency install, collection, and full
   canonical tests from an isolated clone/worktree of that commit;
7. publish the accepted branch so `origin/main` is no longer behind;
8. keep P6 and Clinical Engine integration blocked.

Explicit exclusions: `CORPUS_MANIFEST.json`, `pilot_review_batch/`,
`pilot_review_batch_v2/`, `medical_dictionary/unknown_drugs.csv`, production
or backup DB/SQLite files, all PDFs, local owner exports, unrelated RC-030
historical generated trees, and session scratch files.

After repository reproducibility is closed, the next clinical-governance
work is real reviewer registration and the physician pilot. It must not
auto-approve any regimen or reuse C7 source-fidelity events as clinical
approval.

## Next task after C7 closure — 2026-07-30

C7 owner source-fidelity review is complete. Do not request more C7 owner
answers. Preserve the 182-event final append-only artifact and the explicit
8-label metric-equivalence decision.

Next work is a separate governed P5.6 acceptance audit against
`GOVERNANCE_SOURCE_OF_TRUTH.md`: identify remaining non-C7 acceptance gates,
verify repository reproducibility/credential requirements, and keep P6 plus
Clinical Engine integration blocked. Do not mutate production medical data
or convert source-fidelity events into clinical approvals.

## Immediate owner action: repaired 6068 — 2026-07-30

On `correction_07_source_repair.html`, verify the displayed source
`500¹-1000² мг 3 раза в сутки` and press button `1` if it matches the PDF:
the numeric dose range is `500-1000 мг` per administration; `¹` and `²` are
footnote markers. Then export the `range-single-review` JSON and attach it
for final event validation, supersession reconciliation, and consolidation.

## Immediate next task: governed repair of 6068 — 2026-07-30

Owner correction review is complete. Next:

1. repair the extracted source for `6068` from flattened
   `5001-10002 mg` to visual `500¹-1000² mg` / numeric `500-1000 mg`;
2. rebuild the evidence identity and validation unit without modifying the
   source PDF or production database;
3. present the repaired evidence for a new owner superseding verdict;
4. rerun final consolidation and comparison;
5. explicitly record whether the eight table-aware
   `CORRECT_EXPLICIT_PER_DOSE` labels count as metric-equivalent to
   `CORRECT_RANGE_SINGLE`.

## Retry 5528 with explicit anchor comparison — 2026-07-30

On `correction_06_wrong_anchor_retry.html`, compare the source sentence and
press button `4`. Export `range-single-review` once more. Do not press button
`1`: the displayed `15-20 mg/kg` range is not rifabutin's dose.

## Final substantive owner action: 5528 — 2026-07-30

Open `correction_05_wrong_anchor.html` and choose button `4`: the displayed
`15-20 mg/kg` range belongs to ethambutol, while the target rifabutin dose is
`5 mg/kg once daily`. Export `range-single-review` afterward.

## Current record 5824 — 2026-07-30

For the displayed amoxicillin/clavulanate text, record choice `1` (range per
administration). The phrase `1 or 2 times/day` is frequency and is not a
separate option in this dose-basis review.

## Final owner corrections — 2026-07-30

Complete `correction_04_single.html` for `5528` and `5824`, export the
`range-single-review` JSON, then run final consolidation and comparison.
`6068` remains a separate governed source-repair item.

## Current owner action: erythromycin daily range — 2026-07-30

Complete the single record `5441` on
`correction_03_unit_basis.html`, export the `range-unit-basis-review` JSON,
then proceed to `correction_04_single.html` for the final two records.

## Do not repeat exact page — 2026-07-30

The active page is now `correction_02_engine.html`. Record answers for
`5475` and `5478`, then export `range-engine-review`; do not return to or
re-export `correction_01_exact.html`.

## Current owner action: engine disagreements — 2026-07-30

Complete `correction_02_engine.html` from `0/2` to `2/2` for `5475` and
`5478`, export the `range-engine-review` JSON, then continue to the
single-record unit-basis correction `5441`.

## Current owner action — 2026-07-30

Complete `correction_01_exact.html` from `0/2` to `2/2` by recording one
large-button verdict for each record, then continue to
`correction_02_engine.html`.

## Remaining correction sequence — 2026-07-30

1. `correction_01_exact.html`: `6296`, `6550`;
2. `correction_02_engine.html`: `5475`, `5478`;
3. `correction_03_unit_basis.html`: `5441`;
4. `correction_04_single.html`: `5528`, `5824`.

Corrections `7519`, `7629`, and `7644` are complete and must not be requested
again.

## Immediate owner action: save both correction answers — 2026-07-30

On `correction_01_exact.html`, press one large verdict button (`1`, `2`, `3`,
or `4`) for each of the two records. Confirm that the visible correction
counter changes from `0/2` to `2/2`; merely reading the PDF does not create a
superseding owner event.

## Active owner task: correction page 1 — 2026-07-30

Complete the four correction pages in order:

1. `correction_01_exact.html` — 2 records;
2. `correction_02_engine.html` — 2 records;
3. `correction_03_unit_basis.html` — 4 records;
4. `correction_04_single.html` — 2 records.

After all reach full counters, export the consolidated owner history again,
validate the new supersession chains, and rerun owner-vs-AI/PDF comparison.
Do not include `6068` until its flattened-footnote source is repaired and
revalidated.

## Immediate next task: owner correction mini-batch — 2026-07-30

Create a correction-only review queue without mutating existing events:

1. request superseding owner verdicts for substantive disagreements
   `6296`, `6550`, `5475`, `5478`, `5441`, `7519`, `7629`, `7644`, `5528`,
   and `5824`;
2. repair the source extraction for `6068` from flattened
   `5001-10002 mg` to visual `500¹-1000² mg` / numeric `500-1000 mg`;
3. rebuild and revalidate the repaired `6068` evidence identity before a
   superseding owner verdict;
4. decide explicitly whether table-aware
   `CORRECT_EXPLICIT_PER_DOSE` and generic `CORRECT_RANGE_SINGLE` are
   equivalent for precision metrics, without rewriting immutable events;
5. rerun event validation, consolidation, and owner-vs-AI comparison.

Do not change production DB, calculation eligibility, clinical approval, or
Clinical Engine state.

## Immediate next task: governed export intake — 2026-07-30

Obtain the downloaded owner JSON files. Prefer the latest/largest export for
each of five modes (expected event counts: exact 36, engine 11, unit basis
43, table 8, single candidate 15), or accept all copies and deduplicate them
append-only.

Then:

1. validate every event with the committed owner-event validator;
2. reconcile exactly 113 distinct reviewed regimen IDs;
3. preserve supersession history and reject malformed/test events;
4. quarantine `regimen_id=6068` for footnote-marker source repair;
5. review any other owner/AI/parser disagreements;
6. produce an intake report without changing production DB, calculation
   eligibility, or Clinical Engine state.

## Final owner task: batch 11 — 2026-07-30

Complete `c7_batch_11_single_candidate.html` from `0/3` to `3/3`, export
JSON, then collect all preserved exports for governed validation,
deduplication, and consolidation. Do not infer approval from UI completion.

## Active owner task: batch 10 — 2026-07-30

Complete `c7_batch_10_single_candidate.html` from `0/12` to `12/12`, then
export JSON and proceed to final batch 11 (`3` records).

## Active owner task: batch 09 — 2026-07-30

Complete `c7_batch_09_table_review.html` from `0/8` to `8/8`, then export
JSON. Verify row/column attribution against the visible PDF table; use `3` or
the detailed table-context verdict when headers cannot be attributed safely.

## Active owner task: batch 08 — 2026-07-30

Complete `c7_batch_08_unit_basis.html` from `0/7` to `7/7`, then export JSON.
After this, proceed to the 8-record table-context batch 09.

## Active owner task: batch 07 — 2026-07-30

Complete `c7_batch_07_unit_basis.html` from `0/12` to `12/12`, then export
JSON. Use the same explicit dose-basis rules; do not infer a daily total from
administration frequency alone.

## Active owner task: batch 06 — 2026-07-30

Complete `c7_batch_06_unit_basis.html` from `0/12` to `12/12`, then export
JSON. Continue using `1` for per-administration amounts, `2` for explicit
daily totals (`/сут` or `/день`), and `3` when the source is inconclusive.

## Current dose-basis guidance — 2026-07-30

For batch 05, classify `20–30 мг/кг/день в три приема` as choice `2`: the
range is the total over 24 hours and is then divided among three
administrations. Continue the remaining batch-05 records using the same
source-fidelity rule.

## Active owner task: batch 05 — 2026-07-30

Complete `c7_batch_05_unit_basis.html` from `0/12` to `12/12`, then export
JSON. These records specifically require distinguishing per-administration
from explicit daily-total dose basis; use `3` rather than inferring when the
source is silent.

## Active owner task: batch 04 — 2026-07-30

Complete `c7_batch_04_engine_disagreement.html` from `0/11` to `11/11`, then
export JSON. This batch contains engine/independent-review disagreements, so
use `3` when the source does not establish the basis and the detailed form
for unusual mismatches.

## Active owner task — 2026-07-30

Complete `c7_batch_03_exact.html` from `0/12` to `12/12`, then export JSON
before moving to batch 04. Keep all previously downloaded exports; do not
assume browser-local counters survive a new session.

## Continue with C7 batch 03 — 2026-07-29

Current browser page:
`http://127.0.0.1:8977/c7_batch_03_exact.html` (`0/12`).
Complete all records with buttons `1`–`4`, verify `12/12`, then export JSON.

## Finish the missing batch-02 record — 2026-07-29

The browser is on record 1 of `c7_batch_02_exact.html`, currently marked
unreviewed. Submit one deliberate answer (`1`–`4`), confirm the counter is
`12/12`, then export and proceed to batch 03.

## Continue C7 owner review — 2026-07-29

Current browser page:
`http://127.0.0.1:8977/c7_batch_02_exact.html` (`0/12`).
Complete batch 02 using buttons `1`–`4`, then download JSON again. Preserve
the downloaded batch-01 export and provide it to the assistant before
governed validation/consolidation; UI completion alone is not intake.

## Dose-basis rule shown in the UI — 2026-07-29

Do not classify by frequency alone:

- `500–1000 мг 1 раз в сутки` → choice `1` (the numbers are the dose for
  one administration; it happens once daily);
- explicit `мг/сут`, `мг/кг/сут`, or `суточная доза` → choice `2` (the
  numbers are the total over 24 hours);
- if the source does not establish the basis → choice `3`.

## Simplified owner answers — 2026-07-29

For each record, open the PDF and compare the quote with the purple
**Проверяем именно эту запись** card. Answer with:

- `1` — dose is for one administration;
- `2` — dose is the total for the whole day;
- `3` — the PDF does not make this clear;
- `4` — the numbers belong to another drug.

Use collapsed **Другой случай / ошибка в записи** only when none of these
four answers fits. Export JSON after each batch.

## Immediate PDF-enabled owner workflow — 2026-07-29

The local owner-review server is running at
`http://127.0.0.1:8977/c7_batch_01_exact.html`. Click
**Открыть PDF на нужной странице** before each verdict; it now opens the
source under `/__pdf__/` with the record's `#page=` anchor. Continue with
keys `1`/`2`/`3`, then export JSON after each batch.

If the server must be restarted, use the exact multi-root command in
`RC030_C7_OWNER_REVIEW_LAUNCH_GUIDE.md`; do not revert to
`python -m http.server`, because that server cannot expose PDFs stored
outside the HTML directory.

## Immediate owner workflow — 2026-07-29

Open `http://127.0.0.1:8977/c7_batch_01_exact.html` and review with:

- `1` = range per administration;
- `2` = daily-total range;
- `3` = ambiguous.

Each action saves a standardized source/page note and advances automatically.
Use the detailed form for errors or unusual cases. Export JSON after each
12-record batch. The assistant may then validate and consolidate exports;
it must not generate real owner events.

## Authoritative next actions — 2026-07-29 (post C7 AI pre-review)

Status: AI advisory review covers 113/113 C7 tasks, but genuine owner events
remain 0. Approved objects remain 0, Clinical Engine is disconnected, and P6
remains BLOCKED.

1. Treat `regimen_id=5528` as an open AI finding: do not apply the
   `15-20 mg/kg` ethambutol range to rifabutin. Independently review before any
   authoritative data correction.
2. If the owner continues without human source-fidelity review, retain the
   current DRAFT/BLOCKED state. Do not populate
   `TYPES_MEETING_PRECISION_THRESHOLD`, clinical approval, or engine inputs
   from `RC030_C7_AI_PRE_REVIEW_EVENTS.json`.
3. Product work may continue only on clearly labelled DRAFT/reference
   functionality (coverage, formulations, UX, citations) without claiming
   clinical validation.
4. P6 still requires real reviewers, physician-approved objects, governed
   precision evidence, and explicit owner authorization.

## Authoritative next actions — 2026-07-16 (post RC-030 Evidence Validation)

Status snapshot: approved objects = 0, Clinical Engine disconnected, **P6 remains BLOCKED**.

0. **OWNER: approve or reject staging the sandbox + RC-030 changes.** `DOSE_SANDBOX_PRECOMMIT_AUDIT.md`
   has the proposed allowlist (updated with the Phase 1 two-commit split confirmation). Two separate
   commits recommended (P5.6 sandbox, then RC-030) — not combined, per instruction. Nothing has been
   staged or committed yet.
1. **RC-031: RETRACTED, filed in error.** The claimed drug-name misattribution on regimen 5574 did not
   hold up — re-verification against the live database showed it was correctly labeled all along, and
   the original "mismatch" was a fabricated comparison written during report drafting rather than a
   real database query. No corpus-wide drug-attribution audit was performed. See
   `ROOT_CAUSE_REGISTER.md` (RC-031, retracted) and `RC030_TARGETED_SOURCE_RECOVERY_REPORT.md`
   (corrected) for the full trace, and `PROJECT_STATE.md`'s 2026-07-16 correction entry.
2. **RC-030: verdict B (PARSER IMPLEMENTED BUT NOT VALIDATED — CALCULATIONS BLOCKED).** To reach a
   safe calculation-eligible subset, either (a) run a properly-powered precision validation (hundreds
   of samples per semantic type, not 135) to clear the 99% Wilson-lower-bound threshold and populate
   `dose_verification_sandbox/validation_status.TYPES_MEETING_PRECISION_THRESHOLD`, or (b) pursue the
   schema-level fix recommended in `RC030_SCHEMA_RESPONSIBILITY_DECISION.md` (add `denominator_time`
   to `assembled_regimens` at the assembly layer) and re-validate that implementation independently —
   moving the logic doesn't itself increase precision. See `RC030_EVIDENCE_VALIDATION_REPORT.md`.
3. **RC-030 (original schema gap, still open):** the real fix is still an Architecture Change
   to the P5.3 Regimen Assembly Engine schema (`clinical_engine/regimen/store.py`) — add a
   `denominator_time` column (and max-dose columns) so future assemblies don't need the read-only
   text-reconstruction workaround (`dose_verification_sandbox/semantics_parser.py`) at all. The
   workaround resolves 61.5% of the corpus (87.6% of REVIEW_REQUIRED) but 202 rows remain genuinely
   `AMBIGUOUS` and 74 `UNPARSED` — those need either human resolution via the new Phase 11 ambiguity
   workflow (`dose_verification_sandbox/ambiguity_workflow.py`) or an upstream extraction fix.
   See `RC030_DOSE_SEMANTICS_REPORT.md`.

## Previous next actions — 2026-07-15 (post Review Governance Hardening)

1. **OWNER: register real Reviewer A, Reviewer B, and Medical QA Lead** via `ReviewerRegistry.register(...)` (`clinical_engine/review_workbench/reviewer_registry.py`) with real professional information. Until then `pilot_status = WAITING_FOR_REVIEWERS` — see `REVIEWER_IDENTITY_AND_ASSIGNMENT_POLICY.md`.
2. Once registered, real reviewers may claim/review the 30 activated pilot tasks (`PHYSICIAN_PILOT_ACTIVATION_BASELINE.md`) through the hardened `ReviewService`/API — blinding (`SECOND_REVIEW_BLINDING_SPEC.md`) and the mandatory Medical QA sign-off gate (`MEDICAL_QA_SIGNOFF_SPEC.md`) are enforced end-to-end.
3. Re-run Golden Dataset against physician-approved population when one exists (currently 0 — `GOLDEN_DATASET_APPROVED_ELIGIBILITY.md`).
4. Documentation-only commit still owed for `P56_STAGED_CONTENT_AUDIT.md` and `FRESH_CLONE_REPRODUCIBILITY_REPORT.md` (classified "track" in `POST_RECOVERY_EVIDENCE_CLASSIFICATION.md`), plus this hardening work's own new files, once the pilot reaches a natural checkpoint.
5. Only after P6 entry gates and explicit owner approval prepare P6. Clinical Engine stays disconnected now.

### Superseded (resolved 2026-07-15)
1. ~~OWNER: revoke/rotate exposed provider credentials~~ — done, owner attestation recorded (`API_KEY_ROTATION_VERIFICATION.md`).
2. ~~stage canonical source/docs/tests, commit, verify fresh clone~~ — done, commit `32096af`, `FRESH_CLONE_REPRODUCIBILITY_REPORT.md`.
3. ~~Physicians: start real Review Workbench pilot~~ — blocked pending reviewer registration (item 1 above); three governance defects found and fixed first.
5. Only after P6 entry gates and explicit owner approval prepare P6. Clinical Engine stays disconnected now.

Historical priorities below are superseded where conflicting.

**2026-07-15: P5.5 Clinical Knowledge Type Separation DONE** (`P5.5_IMPLEMENTATION_REPORT.md`).
RC-024 resolved architecturally: new `TherapeuticOption` type for class-level knowledge (652
migrated, 100% provenance). ClinicalRegimen REJECT dropped from 1,119 to 467 (genuine gaps only:
444 extraction + 23 TB-noise/RC-026). 33/33 tests pass. P5.3/P5.4 unmodified; engine untouched.

**Next priorities (revised):**
1. **Populate review/approval workflow for BOTH types** — 1,556 ClinicalRegimen (PASS+REVIEW) + 652
   TherapeuticOption candidates await physician review (`CLINICAL_VALIDATION_FRAMEWORK.md`). Not
   engineering — the actual gate to P6.
2. **Governance decision (lower priority, not a P6 blocker):** should the Clinical Decision Engine
   eventually consume `TherapeuticOption` knowledge? Currently reference-only by design.
3. **Then P6** — cutover per `MIGRATION_PLAN_NORMALIZED_REGIMENS.md`, serving approved
   `ClinicalRegimen` candidates (TherapeuticOption integration deferred, not blocking).
4. **Deferred, tracked, non-blocking:** RC-023 (kb_p44 linkage), RC-025 (quote/drug misalignment),
   RC-026 (TB table extraction), 444 genuine dose/route extraction gaps.

---

**2026-07-15: P5.4 Quality Improvement DONE** (`P5.4_IMPLEMENTATION_REPORT.md`). RC-024 fully audited:
dominant cause (59.6%, 675 regimens) is drug-class/alternatives guideline statements with no single
dose — a regimen-modeling scope question, not a bug. Only 1.1% (13) safely auto-fixable; shipped.
Metrics: REJECT 1132→1119. P5.3 architecture unmodified (additive quality-improvement layer only).

**Next priorities (revised, in order):**
1. **Governance decision on class-level regimens** (new, highest priority — supersedes old RC-024
   framing): should `ClinicalRegimen` support a "class-level recommendation" object type (no single
   dose, lists eligible drugs), or are the 675 such guidelines excluded from the regimen corpus?
   Decides usability of 59.6% of the corpus. Sign-off Authority / Medical QA Lead decision.
2. **Populate approval workflow** — 569 PASS + 987 REVIEW = 1,556/2,675 (58.2%) on a path to
   `PHYSICIAN_APPROVED`; needs physician review capacity, not engineering.
3. **Then P6** — cutover per `MIGRATION_PLAN_NORMALIZED_REGIMENS.md`.
4. **Deferred:** RC-023 (kb_p44 intra-regimen linkage), 31 genuine extraction failures (re-extraction).

---

**2026-07-15: P5.3 Clinical Regimen Assembly Engine IMPLEMENTED** (`P5.3_IMPLEMENTATION_REPORT.md`).
Additive `clinical_engine/regimen/` package + shadow adapter; engine not switched. Measured: 2,675
regimens assembled, 100% explainable-to-source-line, 0 shadow divergence, 14 tests pass.

**Next priorities (in order):**
1. **RC-024 governance decision** — 42% Gate-1 REJECT from NULL-numeric-dose source rows; decide
   REVIEW-vs-REJECT for scheme-based doses before that 42% is written off. Governance/clinical call.
2. **Populate approval workflow** — everything is `REVIEW_REQUIRED` by design (no auto-approval).
   P6 (engine consuming assembled regimens) requires a body of `PHYSICIAN_APPROVED`/`PUBLISHED`
   regimens → physician-review capacity (`CLINICAL_VALIDATION_FRAMEWORK.md`), not engineering.
3. **Then P6** — cutover per `MIGRATION_PLAN_NORMALIZED_REGIMENS.md` (shadow→parity→config flip).
4. **Deferred:** RC-023 (kb_p44 intra-regimen linkage) — unblocks atomic-fact assembly; large
   extraction-layer change, not required for v1.

Prior milestone context (P4.4 certification) retained below.

---

**2026-07-15: P4.4 CERTIFIED.** Full Release Readiness Review executed on the complete 192/192-PDF
rebuild — all Production Gates measured PASS. See `PRODUCTION_SCORECARD.md`,
`PROVENANCE_CERTIFICATION.md`, `P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md`, and the 2026-07-15 entries
in `AI_LOG.md`/`DECISIONS.md` for full evidence. **Code freeze lifted.**

**Next milestone priority — RC-019 (Critical, highest-ranked open item):** the Clinical Decision
Engine (`clinical_engine/`) reads a separate `medical_normalizer.db`/`normalized_regimens.sqlite`,
NOT `kb_p44.db`. P4.4's certified provenance/traceability guarantees do not yet reach served
recommendations. This is P5/P6 scope (see `ENTERPRISE_ARCHITECTURE_REVIEW.md` EAR-1,
`ANTIBIO_ROADMAP_P5_P10.md`, `docs/rfc/P5_KNOWLEDGE_PLATFORM_RFC.md`) — decide the canonical single
knowledge store before building more P5 surface area on top of the split.

**Other registered, non-blocking findings for the next Root Cause cycle** (see
`ROOT_CAUSE_REGISTER.md` for full detail, ranked by benefit/effort):
- RC-008/009 — table-derived entity yield is low (`CKY.tables=1.1%` measured); RC-009
  (`build_knowledge_objects` drops AlternativeTherapy/FirstLineTherapy/AgeRestriction) now confirmed
  by measurement, not hypothesis.
- RC-020 — drug identity triplicated across code/normalizer-DB/KB (motivates a Clinical Knowledge
  Ontology).
- RC-021 — engine's `diagnosis_index.json` is DRAFT/PARTIALLY_CURATED (routing risk).
- RC-022 — status vocabulary drift (`active` vs canonical `draft→validated→published→superseded→
  deprecated` lifecycle) — grows more expensive to migrate the longer it ships.
- RC-011 — `_get_by_key` substring-scan dedup (false-merge/miss risk) — will not scale to P5 query
  load (see EAR-5).

**Design assets already produced, ready for P5/P6 implementation kickoff:**
`GOLDEN_DATASET_SPECIFICATION.md`, `docs/rfc/P5_KNOWLEDGE_PLATFORM_RFC.md`,
`docs/design/CLINICAL_DECISION_ENGINE_DESIGN.md`, `PRODUCTION_QA_PROGRAM.md`,
`ANTIBIO_ROADMAP_P5_P10.md`, `CLINICAL_VALIDATION_FRAMEWORK.md`.

**After P4.4 (now unblocked):** author `PRODUCTION_INVARIANTS.md` — the consolidated guarantees
developers read before any change (owner directive 2026-07-14) — then proceed to P5 per the roadmap,
resolving RC-019 as the first-class deliverable.

**Date:** 2026-07-10

## Current Active Task: P1 — Terminology Binding (Clinical Product Focus)

**P0 COMPLETE + FROZEN.** See P0_COMPLETION_REPORT.md.

Process building phase complete. No new rules. Focus: clinical capability.

**Permanent laws (last ones):**
- Clinical value primary.
- Clinical Evidence Rule.
- Clinical Traceability Rule (law): every rec must answer the 7 questions. No black box.
- Optimization Rule (permanent): Never optimize infrastructure unless it directly improves clinical decision quality, safety, maintainability, or measurable performance.

If no measurable benefit exists, do not change it.

**P1-A Drug Terminology COMPLETE + FROZEN.** See P1_Terminology_Implementation_RFC.md.

**P1-B Diagnosis Terminology:** CLOSED (ACCEPTED + FROZEN). Genuine PASS. 0 failed. Golden PASS. Negative cases now use not_guideline_id to prove incorrect guideline exclusion (in addition to correct guideline_id). P0 pure. P1 dedicated.

**P2-1 Conformance Validator:** COMPLETE + FROZEN. not_guideline_id + trace_code added. Negative cases now prove exclusion. All A/B resolved.

**P3 — Clinical Data Curation (current):** 
- Diagnosis index → PRODUCTION_CURATED (resolve 101 conflicts).
- Expand diagnosis_synonyms.json (peds, chronic, variants).
- Structure renal_adjustment (JSON rules not text).
- Populate drug_atc.json (physician review).
- 300-500 clinical Golden Cases as evidence base.
No architecture. No engine logic. Only medical content + docs + tests.

**Regimen Review Workbench status (2026-07-11):** ready for safer repeated physician queue generation. Default run modifies no ledger and no upstream corpus; only `.md`/`.csv` artifacts are written. Use `python -m clinical_engine.tools.regimen_review_workbench --update-ledger` only when physician-review ledger scaffolding is intentionally desired. Latest measured queue: 305 kept, 138 keyword-tier false positives excluded (previous artifact 438 queued). Rows sort by area → priority → diagnosis → regimen_id. Next: physician reviews generated artifacts; AI may adjust tooling/config only on explicit request, without inventing medical content.

**Frozen Components**
- Architecture v3
- BundleManifest + schema + validator
- Provider Ports
- Bundle Loader
- Engine invariants
- Medical Normalizer / SQLite / Dictionary
- Traceability + Optimization + Evidence rules
- P1-A Drug Terminology (TerminologyProvider)

**Current Milestone**
P1 — Terminology Binding (P1-A FROZEN, P1-B CLOSED ACCEPTED FROZEN)

**Active Issue**
P1-B CLOSED (ACCEPTED + FROZEN)

**Workflow Stage**
P1-B PASS after independent review. Genuine.

**Current Test Status**
Full suite: `python -m pytest -q` → 1266 passed, 1 xfailed, 1 warning (2026-07-11). Workbench targeted: 10 passed.

**Next Implementation Step**
P2-1 CLOSED. P2-2 Analysis ONLY done (doc). Handoff complete. STOP. No impl P2-2 or later. See backlog for queue.

NEXT MILESTONE

P4 — Document Intelligence Platform ✅ COMPLETE + Production Ready (mechanics; 4.1-4.3)

**2026-07-13: P4.5 FINAL CLINICAL ACCEPTANCE AUDIT — PASSED (A)**

Strict 12-step audit complete (real execution only):
- 193 PDFs corpus reprocessed via production_reprocessor.py (resume/metric collection validated).
- Clinical extraction (Drug/Dose/Dur/Freq/Alt/First-line/Preg/Ped/Renal/Contra) measured from structured TableCell grids.
- Before/after + completeness table vs baseline (table_dependency_audit): 20 structured tables recovered on table-heavy PDFs; clinical signals (dose/alt/ped cells) now extractable.
- 0 false positives. Reprocessor + layout exercised on real (sepsis newborn, TB, aorto, otitis candidates).
- Regressions clean (11 passed prior + current). Engineering audit PASS.
- Full P4.5_PRODUCTION_AUDIT.md produced with required report table + verdict.

**Verdict:** A) P4.5 PASSED. P4.4 Production Knowledge Base may begin (use structured tables + reprocessor for improved corpus freeze).

**Next Implementation Step (P4.4 Production Knowledge Base Platform — CURRENT):**
- Run `python build_p44_kb.py --full` (or batches) for full 193-PDF corpus.
- Triage reviews/conflicts from real layout data.
- Complete regression (suites launched).
- Finalize P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md with full measured stats.
- Sync all docs.
- Declare complete when `kb_p44.db` is verifiably the single authoritative source.

See P4.4_PRODUCTION_KNOWLEDGE_BASE_REPORT.md (116 objects measured, rich model + tooling delivered).

P4.4 Production Knowledge Base (mechanics) ✅ COMPLETE (real)

- Versioned immutable KObjects
- Lineage, dedup, conflict, merge, review, validation, impact
- Real benchmark on guideline PDFs (100+ objs, reviews/conflicts)
- No forced KG

**Order per audit:** Layout (P4.5) data quality first → then authoritative P4.4 KB population. P4 complete (mechanics). Next: P4.5 enablement + P5 on improved data.

See table_dependency_audit_2026-07-13.md, AI_LOG, DECISIONS, PROJECT_STATE.

Strategy (adopted):
P4 Doc Intel ✅
P5 Knowledge Platform (incl P4.4 + full KB)
P6 Clinical Decision
P7 Production

Future rule: every rec + separate validation prompt + real audit before close.

No Clinical Engine changes.

**P4.1 note:** COMPLETE (see PROJECT_STATE). Full corpus validation (947 unique PDFs) done in P4.1.1.

Future rule (per project guideline): Every new recommendation must be accompanied by a separate validation prompt for production audit. Cycle: Analysis/design → Implementation → Real production validation → Update ROADMAP/PROJECT_STATE/AGENTS/DECISIONS/AI_LOG/etc. → Readiness report.

**Clinical questions for P1:**
- How does ATC/terminology improve physician decision quality?
- Which real clinical scenarios (e.g. allergy + CAP) become better?
- Golden Cases for validation?
- How doctor sees the trace (terminology mapping)?

**Future note (post P1):** Consider Golden Clinical Dataset (clinical_validation/ with real cases for auto-checks).

See P0_COMPLETION_REPORT.md for baseline.

**P1 Goal (clinical):** Standardize terminology for better safety (allergy via ATC), diagnosis binding, future layers. Demonstrate clinical benefit with examples, not just coverage.


---

## (архив) Clinical Data Quality Audit — реестр pending_review, правок НЕТ

**Артефакты:** `clinical_data_issues.json` (реестр, 4506 записей, `pending_review`), `clinical_data_audit_report.md` (итог), инструмент `clinical_engine/tools/clinical_data_audit.py` (read-only).

**Итог (294 guideline):** Golden-Ready кандидатов **41**; Extraction-ошибки 235 guideline; Normalizer 166; Dictionary 224; переэкстракция 83. PDF-подтверждён только 1638; остальное — heuristic_flag.

**Ждёт решения пользователя (ничего не исправляю автоматически):**
1. Приоритет исправлений пайплайна (кандидаты по макс. приросту: словарь 1166 / парсер длительности 623 / парсер суточной дозы SAFETY 61 / переэкстракция 83).
2. Нужна ли полная построчная PDF-сверка КР↔ANTIBIO (сейчас только heuristic + 1638 confirmed).
3. Начинать ли Golden Cases с 41 Golden-Ready кандидата (после финальной PDF-сверки конкретного guideline).

---

## ⛔ ИНЖЕНЕРНАЯ ФАЗА ЗАМОРОЖЕНА (2026-07-10, решение пользователя)

**Больше НЕ добавлять функциональность. Не начинать Milestone 14+. Не «улучшать ради улучшений».** Роль агента — Reviewer/QA (см. `AGENTS.md` §0.1). Дальше — не программирование, а клиническая проверка и подготовка к реальному использованию. Агент ждёт конкретной QA/review-задачи.

**RFC H1 — CLOSED for v1** (подтверждено пользователем; пересмотр только при реальной необходимости Flutter, v1.1).
**Git baseline — задача пользователя, не агента:** `git add / commit / tag v1.0.0-engine` по `RELEASE_READINESS.md`.

### Дальнейший план (очередь ВРАЧА, не агента):
1. **Курировать `diagnosis_index`** — врач заполняет `diagnosis_index_decisions.json` (101 конфликт) → `build_curated_index` → `PRODUCTION_CURATED` (иначе Production Guard не пустит под strict).
2. **Написать 20–30 Golden Cases** по частым нозологиям: острый средний отит, острый бактериальный риносинусит, стрептококковый тонзиллит, внебольничная пневмония, цистит, пиелонефрит, рожистое воспаление, инфекции кожи/мягких тканей, H. pylori и т.д. Формат — `clinical_engine/golden_cases/README.md` + `_TEMPLATE.json`.
3. **Прогнать движок на кейсах** — `python -m clinical_engine.golden_cases.runner`. Разбор PASS/FAIL — задача агента (Reviewer/QA): объяснить причину расхождения (движок / данные / кейс / неоднозначность КР), НЕ исправлять автоматически.
4. **Верифицировать `allergy_class_map`** (17 классов).
5. **Только после этого — Flutter.**

### Статус (справочно):
M1-8 + M9 + Perf Audit + M10 + M11 + M12 + M13 (Release Readiness) ✅. Дефолтный `pytest` → **1141 passed, 1 xfailed**, no regression.

### Milestone 13 — Release Readiness (done ✅):
- **Production Guard:** Engine под `strict_mode=True` отказывается стартовать на некурированном индексе (`RESOURCE_NOT_CURATED`); non-strict → warning. `Profiles.production`=strict.
- **Test discovery:** дефолтный `pytest` покрывает все подсистемы; extractor помечен `xfail` (не исправлялся).
- **RFC H1:** переоценён → рекомендация закрыть для v1 без изменений (ждёт решения пользователя).
- **Git:** рекомендации в `RELEASE_READINESS.md`; ничего не коммитил.

### СЛЕДУЮЩИЕ ШАГИ — вне AI (требуют реального врача) + решения пользователя:
1. **Решение пользователя:** формально закрыть RFC H1 (рекомендация — закрыть для v1).
2. **Первый release-commit** по `RELEASE_READINESS.md` (git baseline + тег `v1.0.0-engine`) — по вашему решению.
3. **Курация индекса (M11):** врач заполняет `diagnosis_index_decisions.json` → `PRODUCTION_CURATED` (иначе Production Guard не даст запуститься под strict).
4. **Golden cases (M12):** врач пишет кейсы в `clinical_engine/golden_cases/*.json`.
5. Врачебная верификация `allergy_class_map` (17 классов).
6. Клинические решения AI-агент НЕ принимает.

### Отложенные технические решения (ждут review):
- Оптимизация `RegimenLoad` (~69% pipeline, L7) — цели §9.1 уже выполнены
- Flutter integration — только после всей верификации

### Более ранние milestone (done ✅) — история в `AI_LOG.md` / `DECISIONS.md`:
M10 (анализ конфликтов), M11 (механизм курации: `tools/build_decision_ledger.py` + `build_curated_index.py` + `PHYSICIAN_VALIDATION_GUIDE.md`), M12 (golden cases infra: `clinical_engine/golden_cases/` + runner + 13 тестов).

### Performance Audit — done ✅ (ждёт review отчёта):
- Инструменты `clinical_engine/tools/`: `build_diagnosis_index_draft.py`, `build_normalized_sqlite.py`, `performance_audit.py`
- Draft `diagnosis_index.json` (AUTO_GENERATED_DRAFT): 895 записей, 294 guideline_id, 101 конфликтующий mapping — требует врачебной курации
- `normalized_regimens.sqlite` построена из 2675 схем (PASS 1039/REVIEW 443/REJECT 1193)
- Результат: все цели §9.1 выполнены (init ~29ms, recommend max <18ms, ~2540 recs/sec). **Bottleneck RegimenLoad ~69%** (L7 повторный lookup + drug_ref resolve). Отчёт `performance_audit_engine.md`
- **Оптимизацию НЕ проводил** — ждёт review, потом решение

### Следующее — Golden Clinical Cases (§10.1 Tier 3):
1. Каркас для doctor-verified input/output пар (`GoldenCase` dataclass, тест-раннер) — инфраструктуру могу сделать я
2. Сами кейсы (ожидаемый препарат/линия/route/exclusion) — **требуют врачебной верификации**, не могут быть сделаны AI-агентом в одиночку
3. Примеры из спеки §10.1: CAP adult → amoxicillin first-line; Doxycycline + pregnancy → excluded; Penicillin allergy → все beta-lactams excluded
4. **Важно:** golden cases зависят от draft `diagnosis_index.json` (некурированный, 101 конфликт) — до врачебной курации индекса golden cases будут нестабильны для diagnosis-based lookup. Возможно, сначала курация индекса

### Отложенные решения (ждут review/врача):
- Оптимизация `RegimenLoad` (устранить повторный `diagnosis_provider.lookup()`, батч-загрузка) — perf bottleneck, но абсолютные числа уже в пределах цели
- Врачебная курация draft `diagnosis_index.json` (101 конфликт) → production-версия + `guideline_version` в metadata
- Врачебная верификация `allergy_class_map` (17 классов)
- RFC H1 (per-recommendation trace/Evidence §7.5 — изменение frozen-моделей)
- Flutter integration — только после всей верификации

### Milestone 9 — audit remediation (done ✅):
- Кодом: M1 (allergy hardening: case-insensitive + `ALLERGY_UNVERIFIABLE`), M3 (package-anchored пути), M5 (типизация reader'ов), L1 (`_population.py`), L2/L4/L8
- Документацией: M2 (неточная запись), H1+M4 (per-recommendation trace/Evidence §7.5 → RFC, ждёт approval — требует `StageTrace.regimen_id` + `DecisionCode.EVIDENCE`, изменение frozen-моделей)
- 222 теста, +3 из M1. См. `DECISIONS.md` "Milestone 9 — audit remediation"

### После Performance Audit (план пользователя):
- **Golden Clinical Cases** (§10.1 Tier 3) — doctor-verified input/output пары. Требует участия врача
- **Production `resources/diagnosis_index.json`** — курация ~294 записей (разблокирует `guideline_version` в metadata + реальный DiagnosisMatch)
- **Врачебная верификация** `allergy_class_map` (17 классов, draft)
- **RFC H1** — решение по per-recommendation trace/Evidence (изменение frozen-моделей)
- **Flutter integration** — только после всей верификации

**Важно:** Clinical Decision Engine реализован независимо от v0.5 (ATC)/v0.6 (LLM re-extraction) — см. `DECISIONS.md` "roadmap order superseded". Dictionary/ATC задачи ниже остаются в очереди отдельно.

### Milestones 1-8 (done ✅) — история в `AI_LOG.md` / `PROJECT_STATE.md`:
Все 10 стадий реализованы. Ключевые решения по каждому milestone — в `DECISIONS.md`.

**Список never-populated полей и осознанно отложенного** (confidence §7.3, plugin hooks, 4 score profiles, guideline_version, data gaps) — консолидирован в `DECISIONS.md` (запись "RFC — per-recommendation audit trail", M4).

### Правило (см. DECISIONS.md 2026-07-10):
Architecture FROZEN. Не пересматривать архитектурные решения в одностороннем порядке. Если реализация вскрывает проблему — остановиться, задокументировать, предложить RFC, ждать подтверждения.

---

## [ОТЛОЖЕНО, не блокирует Clinical Decision Engine] Фаза: Medical Data Quality Improvement — Manual Review pending

**Статус:** Medical Dictionary subsystem создан ✅ (terminology DB extracted from Python, no regression). Parser Improvements (Tasks 1-4) завершены ✅ measured.
**Приоритет:** Человек ревьюит 441 candidate → потом dictionary expansion + ATC mapping.

### Medical Dictionary subsystem (2026-07-09) ✅
- `medical_dictionary/` — 10 JSON + loader.py + __init__.py
- `dictionary.py` rewritten: loads JSON via `medical_dictionary.loader`, module-level names preserved, class logic unchanged
- `unknown_drugs.csv` — 441 unknown drugs ranked by occurrence
- `dictionary_candidates.json` — 441 candidates, ALL `pending_review` (never auto-accept)
- Tests: 823/823 pass (+20 loader tests)
- Measured: PASS 1039, REVIEW 443, REJECT 1193, conf 0.7188 — identical to pre-refactor (no regression)

### Parser Improvements results (measured, см. `quality_audit_after_parsers.md`):
- PASS 880→1039 (+159), REVIEW 320→443 (+123 REJECT→REVIEW), REJECT 1475→1193 (-282)
- Confidence 0.6312→0.7188 (+13.9%), parser errors 20→0 ✅
- 2168 fields recovered (freq -454, dur -627, tl -1067, dose -20)
- Tests 726→823 (+97, all pass, TDD)

### Parser improvements status:
- FrequencyParser: 83% recovered (454/547), 93 unparsed edge cases
- DurationParser: 74% recovered (627/842), 215 unparsed edge cases
- TherapyLineParser: 100% (1067/1067)
- Type guards: 100% (20/20 → 0)
- **Parser improvements исчерпаны ~71% (285/403 REJECT-flippable).** Оставшиеся 118 — hard edge cases, diminishing returns.

### Следующие задачи (по priority):

#### Critical (REVIEW↓ + PASS↑, low cost) — СЛЕДУЮЩИЕ (после manual review)
1. **Manual review of 441 candidates** (человек)
   - Файл: `medical_dictionary/dictionary_candidates.json`
   - Каждый candidate: original, normalized_candidate, occurrences, possible_atc, confidence, source_examples
   - Решение: `accepted` / `rejected` (статус в JSON)
   - Никогда не auto-accept
2. **DRUG_SYNONYMS expansion** (по accepted candidates)
   - Источник: accepted entries из dictionary_candidates.json → drug_synonyms.json
   - 438 drug-only REVIEW flippable → PASS
   - REVIEW 443 → ~5-50
   - TDD: tests для каждого new synonym
3. **DRUG_ATC mapping** (по accepted candidates с possible_atc)
   - accepted entries → drug_atc.json
   - DrugParser ATC lookup (через `_coerce_str` helper уже есть)
   - ATC 0% → ~80%, confidence↑
   - TDD: tests для ATC lookup

#### High (REJECT↓, high cost) — отдельный проект v0.6
4. **LLM Re-Extraction v2**
   - 961 LLM-only REJECT (80.6% of remaining REJECT) — raw поля отсутствуют
   - Переписать extraction prompt, re-run 294 PDF, пересобрать KB, re-normalize
   - Цель: REJECT 44.6%→~25%
   - **НЕ начинать автоматически** — decision point после dictionary/ATC

#### Medium/Low
5. Remaining parser edge cases (118 parser-flippable REJECT, diminishing returns)
6. Drug groups handling (фторхинолоны → ATC group J01MA)
7. Combination drug normalization ([...] brackets)
8. Typo correction
9. Real LLM validation (replace mock, 130 IDs)
10. Golden case tests (app)
11. PostgreSQL migration (for >10k)
12. Multiprocessing (for >50k)
13. CI/CD pipeline

### Важно:
- **НЕ модифицировать** architecture (FROZEN), FROZEN модули (models/confidence/validator/normalizer/db)
- **МОЖНО** additions в `medical_dictionary/*.json` (source of truth), `drug_parser.py` (ATC lookup)
- `dictionary.py` — только data-loading layer, class logic FROZEN
- TDD для всех изменений: failing test → implement → verify → measure
- После каждого step: `pytest medical_normalizer/tests/ -q` (823 pass) + measure delta
- Measure, don't estimate

### Ожидаемый результат после dictionary + ATC (tasks 2-3):
- REVIEW: 16.6% → ~2-5% (438 drug-only → PASS)
- PASS: 38.8% → ~55% (+438)
- REJECT: 44.6% (без LLM re-extraction не снижается существенно)
- ATC: 0% → ~80%
- Confidence: 0.7188 → ~0.75

### Для REJECT 44.6%→25% (цель):
- Необходим task 4 (LLM re-extraction v0.6) — high cost, отдельный проект
- 961 LLM-only REJECT — единственный путь
