# RC030_EVIDENCE_VALIDATION_REPORT.md

Date: 2026-07-16
Scope: RC-030 Evidence Validation and Safe Closure

## 1. Reported initial coverage (as claimed before this validation)

"1,645 of 2,675 rows (61.5%; 87.6% of `REVIEW_REQUIRED`) resolved to an explicit dose semantic; 202
`AMBIGUOUS`; 74 `UNPARSED`; 10/12 pilot cases calculable; 66 tests pass." This framing described
parser output as "resolved," implying correctness that had not actually been checked against source
text independently of the parser itself.

## 2. Corrected terminology

Parser output is now called `PARSER_CANDIDATE`, not "resolved." A separate `validation_status` field
records what kind of check (if any) has actually confirmed a candidate. A separate
`calculation_eligibility` field records whether a record may be treated as safe to calculate — see
`dose_verification_sandbox/validation_status.py` and `RC030_CORRECTED_FULL_CORPUS_REPORT.md`.

## 3. Rule catalog

Every regex/rule in the classifier is documented with ID, exact pattern, positive/negative examples,
precedence, and known gaps in `RC030_RULE_CATALOG.md`. Notably documents that table-boundary and
sentence-boundary detection are **not implemented** (source schema has no table structure; sentence
detection was added only as part of the Phase 3 independent audit, not the classifier itself).

## 4. Manual validation design and 5. precision by semantic type

135 rows sampled and independently re-read against `source_quote` (not the parser's own output) —
smaller than the requested 380, stated plainly in `RC030_PRECISION_METRICS.md`. Point-estimate
precision was high (93.3–100% across six strata) but **no stratum's Wilson 95% lower bound reached
the required 99% threshold** — the largest achievable lower bound at 15/15 correct is ~79.6%,
a direct consequence of sample size, not classifier quality. Per the task's own rule, this means
**every semantic type remains below the automated-calculation threshold**, regardless of how clean
the samples looked.

## 6. False-positive analysis

An independent (non-parser) structural risk audit (`semantics_risk_audit.py`) flags boundary-crossing
hazards the classifier itself doesn't check for. Result: 307 of 1,645 pre-fix `PARSER_CANDIDATE` rows
(18.7%) carry at least one risk factor (`COMPETING_DOSE_NUMBER_BETWEEN` 263, `CROSSES_ALTERNATIVE_BOUNDARY`
46, `CROSSES_DRUG_NAME_BOUNDARY` 40, `MIXED_AGE_GROUP_LANGUAGE` 10, `CROSSES_SENTENCE_BOUNDARY` 7). A
manual spot-check of 15 flagged rows confirmed the audit itself was not over- or under-triggering in
that sample. **Building this audit itself required fixing a bug in the audit's own gap-measurement
logic** (it was initially counting the dose token's own digits as a "competing dose," inflating the
flag rate from 18.7% to a spurious 60.4% before the fix) — documented in `RC030_FALSE_POSITIVE_AUDIT.md`.

## 7. 12-case pilot evidence

Full source-quote-level re-read of all 12 original pilot cases plus a dedicated analysis of regimen
5574 (cited separately, not one of the formal 12) — `RC030_12CASE_REVALIDATION.md`. 10/12 confirmed
correct on manual re-read; 2/12 correctly remain blocked (compound units). **One case (regimen 5376)
revealed a genuine calculation-safety bug**: `frequency=3/7` (3×/week) applied to the
daily÷frequency formula produced a single-dose value (210 mg) larger than the daily total (90 mg) —
a mathematical impossibility. Fixed (`SUB_DAILY_FREQUENCY` block in `calculator.py`), affecting 42
rows corpus-wide. Regimen 5574 is proven, from two independent textual markers in a single
self-contained sentence, to mean "50 mg/kg/day, divided into 2 doses" — not "50 mg/kg/dose twice
daily" — a genuinely unambiguous case, not a coin-flip resolution.

## 8. Multi-engine recovery yield

Scoped down from "select a representative pilot" to one case, given the effort budget —
`RC030_TARGETED_SOURCE_RECOVERY_REPORT.md` states this plainly rather than claiming broader coverage.
The one case attempted (regimen 5574's source PDF) confirmed the real source document (`Урогенитальные
заболевания, вызванные Mycoplasma genitalium.pdf`, page 16, after ruling out a same-titled decoy
document) and confirmed its text matches `assembled_regimens`' `source_quote` and `antibiotic`
("джозамицин") exactly — no defect found. **Correction**: an earlier version of this report claimed a
drug-name mismatch here (filed as RC-031), based on a fabricated comparison quote written by hand
rather than copied from the live database. RC-031 has been retracted — see `ROOT_CAUSE_REGISTER.md`
and the corrected `RC030_TARGETED_SOURCE_RECOVERY_REPORT.md` for the full trace of how that error
happened. Full six-engine (PyMuPDF/MinerU/Docling/DocLayout-YOLO/Table Transformer/RapidTable)
reconciliation was **not** performed (out of scope for this pass); RapidTable was not even installed
in this environment.

## 9. Max-dose validation

All 26 (not a sample — the complete population) source-backed max-dose extractions manually
reviewed: all 26 correctly attributed to their own regimen (no cross-drug, no cross-age-group, no
range-upper-bound-mislabeled-as-max cases found). One cosmetic labeling inconsistency found (same
cap attached to `max_single_dose` vs `max_daily_dose` on near-identical regimens, numerically
equivalent since `frequency=1` in both). See `RC030_MAX_DOSE_VALIDATION.md`.

## 10. Schema responsibility decision

Assessed four options (extraction layer / normalizer layer / canonical assembly layer / additive
enrichment layer). **Decision**: the additive enrichment layer (what was built) is correct for a
read-only QA sandbox; the canonical assembly layer (`clinical_engine/regimen/store.py`) is the
correct long-term home, requiring owner/governance sign-off and its own precision re-validation before
being trusted more than the sandbox — not implemented here. See
`RC030_SCHEMA_RESPONSIBILITY_DECISION.md`.

## 11. Corrected corpus metrics

`RC030_CORRECTED_FULL_CORPUS_REPORT.md`: 1,611 `PARSER_CANDIDATE` rows (60.2%, revised down from
1,645 after the `dose_token_located` fix), of which 1,304 are `RULE_VALIDATED` — but **0 rows** are
`calculation_eligibility = QA_ELIGIBLE`. 100% of the corpus remains `BLOCKED` for calculation purposes,
by design, until a properly-powered precision validation exists.

## 12. Remaining ambiguous data

236 rows remain genuinely `AMBIGUOUS` (up from 202 pre-fix, reflecting the corrected classification);
74 remain `UNPARSED`. Both correctly fail closed. The Phase 11 ambiguity workflow
(`ambiguity_workflow.py`, unchanged from the prior RC-030 pass) remains available for human
resolution of these, one at a time, with full provenance.

## 13. Commit split plan

Two separate commits, neither staged: **Commit A** (P5.6 sandbox core, unchanged, works standalone,
fails closed without the semantics layer) and **Commit B** (RC-030 semantics/validation layer). One
shared file (`calculator.py`'s `apply_max_dose` signature extension) recommended to ship in Commit B.
Full allowlists in `DOSE_SANDBOX_PRECOMMIT_AUDIT.md`. **Nothing staged or committed by this
validation pass.**

## 14. Safety invariants (all reconfirmed at the end of this pass)

- `assembled_regimens.sqlite`, `kb_p44.db`, `kb_final.db`, `review_workbench_p56.sqlite` SHA-256
  hashes byte-identical to the Phase 0 baseline.
- `assembled_regimens` rows with `status='APPROVED'`: 0.
- `review_workbench_p56.review_tasks` rows with non-empty `consensus_result`/`qa_verdict`: 0.
- No `clinical_engine` import anywhere in `dose_verification_sandbox/` (test-enforced).
- 83/83 sandbox tests pass; canonical `pytest` full suite exits 0.

## 15. RC-030 status

**PARTIALLY CLOSED, now with independently-validated evidence rather than parser self-report.**
Three real bugs found and fixed during this validation itself (dose-token-location guard, sub-daily
frequency block, risk-audit gap-measurement bug) — proof the validation process was substantive, not
a rubber stamp. A fourth apparent finding (RC-031, drug-name misattribution on regimen 5574) was
**filed in error and subsequently retracted** — see `ROOT_CAUSE_REGISTER.md` — after re-verification
showed the database was correct all along and the mismatch had been fabricated during report
drafting, not measured. That correction is itself now part of this validation's record.

## 16. P6 status

**Remains BLOCKED.** Approved-object count is 0, confirmed unchanged. Clinical Engine remains
disconnected (unchanged — this validation never imports or invokes it). Nothing in this validation
pass — or in RC-030 generally — moves any regimen closer to physician approval or Clinical Engine
connection.

---

## Final verdict

**B) RC-030 PARSER IMPLEMENTED BUT NOT VALIDATED — CALCULATIONS BLOCKED**

The parser's point-estimate quality is good (93–100% correct across every stratum manually checked),
and three real correctness bugs were found and fixed in the course of checking it — but "checked on
135 samples and looked clean" is not the same claim as "validated to 99% precision," and the
task's own threshold rule is explicit that the latter is required before treating output as
calculation-eligible. No semantic type crosses that bar with the evidence gathered in this pass.
Every record in the corpus is therefore `calculation_eligibility = BLOCKED`, enforced in code
(`validation_status.py`), not just in this document's prose. Getting to verdict A would require
either a much larger validation sample (hundreds per stratum) or a different, statistically
adequate acceptance methodology — both out of scope for this pass.

**P6 remains BLOCKED.**
