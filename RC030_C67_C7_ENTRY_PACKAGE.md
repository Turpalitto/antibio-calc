# RC-030 / C6.7 Part XII — C7 Entry Package

## Owner review workload report (Phase 20)

| Category | Count | Queue |
|---|---|---|
| Exact-link confirmation (retained) | 53 | Queue A |
| Single-candidate, simple confirmation | 26 | Queue B |
| Single-candidate, table review needed | 8 | Queue B |
| Single-candidate, alternative-basis review | 2 | Queue B |
| Single-candidate, phase-split needed | 1 | Queue B |
| Single-candidate, wrong-anchor (likely reject) | 2 | Queue B |
| Single-candidate, not-a-range (likely reject) | 2 | Queue B |
| Single-candidate, source-blocked (cannot review as-is) | 2 | Queue B |
| **Queue A + Queue B total** | **96** | |
| Exact-link, downgraded-ambiguous (excluded from both queues) | 13 | none |
| Exact-link, downgraded-table-required (excluded from both queues) | 5 | none |
| Exact-link, rejected-wrong-anchor (excluded from both queues) | 2 | none |
| Exact-link, engine-review-required (excluded from both queues) | 1 | none |
| **Total candidate pool** | **117** | |

**Gap flagged, not resolved unilaterally:** the 21 non-retained exact-link records (13+5+2+1) currently have **no owner queue at all** — they are neither confirmation-ready (Queue A excludes them by design) nor single-candidates (Queue B is scoped to the 43 by definition). Whether these 21 should get a third queue, be folded into Queue B's grouping, or wait for engine fixes before any owner time is spent on them is an **architecture/owner decision**, not something this audit resolves by inventing a third queue unauthorized.

**Table cases requiring tooling before review:** 13 (8 single-candidate + 5 excluded exact-link) — none of these can be meaningfully reviewed without table-layout reconstruction (Phase 10), which is not installed in this environment. Recommend deferring these until that tooling exists, rather than asking the owner to eyeball flattened table text.

**Multi-drug / phase / maximum-conflict cases:** 1 phase-split (5726), 2 wrong-anchor (5526, 5533 — competing-drug range misattribution), plus 6133 and 5678 among the excluded 21 (maximum-clause and 3-way-competing-range cases respectively).

**Source-blocked (cannot be reviewed against cited source at all):** 2 (5688, 6052 — quote not found anywhere in the cited 75-page PDF; needs re-sourcing, not review).

**Physician-level review (as opposed to source-fidelity review):** none identified in this pool — every open question found by this audit is a *source-attribution* question (does the text say what the record claims), answerable by comparing text to record, not a clinical-judgment question about whether a dose is appropriate. This distinction matters for Phase 21's "why source-link precision is not clinical dosing accuracy" framing below.

**Suggested review order:** Queue A (53, highest confidence, fastest) → Queue B simple-confirmation (26) → Queue B alternative-basis (2) → Queue B phase-split (1) → Queue B wrong-anchor/not-a-range (4, likely quick rejects) → Queue B source-blocked (2, flag for re-sourcing, not a real review) → defer all 13 table cases until table tooling exists.

**Estimated minimum owner workload** (rough, unvalidated time-per-record assumption — 2.5 min for a simple single-check confirmation, 4-8 min for anything requiring reading competing candidates): roughly 132 + 65 + 12 + 8 + 16 + 6 ≈ **240 minutes (~4 hours)** for the 83 non-table, non-excluded records in Queues A/B. Table cases and the 21 excluded exact-link records are not included in this estimate since they are not yet review-ready.

## Precision metric policy (Phase 21) — OWNER_SOURCE_FIDELITY_PRECISION

**Scorable verdicts:** only `CONFIRMING_VERDICTS` (`CORRECT_RANGE_DAILY`, `CORRECT_RANGE_SINGLE`, and the other four non-range `CORRECT_*` values, in case a reviewer determines a "range" record is actually a fixed dose) and `ERROR_VERDICTS` (`WRONG_DOSE_ANCHOR`, `WRONG_ALTERNATIVE`, `WRONG_TABLE_ROW`, etc.) enter the denominator — this mirrors the existing, already-governed `PRECISION_SCORABLE_VERDICTS` set in `verdict_taxonomy.py`, unchanged by this program.

**Excluded from scoring:** `UNRESOLVED_VERDICTS` (`REMAINS_AMBIGUOUS`, `TABLE_CONTEXT_REQUIRED`, `NOT_A_DOSABLE_REGIMEN`) and `SOURCE_BLOCKED_VERDICTS` (`SOURCE_INCOMPLETE`, `SOURCE_CORRUPTED`) — reported separately, never counted as correct or incorrect. This matters concretely here: the 2 source-blocked records (5688, 6052) and any reviewer who correctly lands on `REMAINS_AMBIGUOUS` for a genuinely basis-unresolved unit-flagged record must **not** be forced into the denominator.

**Superseded events:** unchanged — `review_decisions.supersedes_decision_id` (already in the `review_workbench_p56.sqlite` schema) handles this; a later decision on the same `task_id` supersedes an earlier one, and only the latest is scored.

**Queue A and Queue B analyzed separately:** required, not optional — Queue A's precision estimates the *engine's* exact-link admission accuracy (53 records the engine and two independent audits already agree on); Queue B's precision (if ever scored — Queue B records are never migration-safe regardless) would estimate something different: how often a `SAFE_SINGLE_CANDIDATE` classification, once disambiguated by a human, turns out plausible vs. wrong. Mixing the two denominators would conflate two different questions.

**Why source-link precision is not clinical dosing accuracy:** every verdict here (`CORRECT_RANGE_DAILY`, `WRONG_DOSE_ANCHOR`, etc.) answers "does the stored range/antibiotic pairing match what the cited source document actually says," not "is this an appropriate or safe dose for this patient population." A 100% `OWNER_SOURCE_FIDELITY_PRECISION` would mean the database faithfully reproduces its cited sources — it says nothing about whether those sources' recommendations are themselves clinically sound, current, or applicable to a given patient. This is why `calculation_eligibility` and `clinically_approved` remain independent, separately-gated fields that this metric does not and cannot satisfy.

## Sample-size proposals (Phase 22)

Wilson-score lower-bound precision estimates (95% CI, z=1.96) for candidate N values, at 0/1/2/3 observed errors — illustrative only, no threshold selected:

| N | 0 errors | 1 error | 2 errors | 3 errors |
|---|---|---|---|---|
| 20 | 0.839 | 0.764 | 0.699 | 0.640 |
| 30 | 0.886 | 0.833 | 0.787 | 0.744 |
| 50 | 0.929 | 0.895 | 0.865 | 0.838 |
| 53 (= full Queue A) | 0.932 | 0.901 | 0.872 | 0.846 |
| 74 (= original pre-audit exact-link count) | 0.951 | 0.927 | 0.907 | 0.887 |

Notes:
- N=74 no longer represents "the exact-link pool" after this audit — it now represents the *original, unaudited* count; the audited pool is 53. Using N=74 as a sample-size target would silently include the 21 records this audit already found reason to exclude, which is not the same statistical claim as "we reviewed the audited pool."
- N=53 (full Queue A) gives a Wilson lower bound of 0.932 at zero observed errors — reviewing the *entire* retained exact-link queue is a defensible target precisely because it is a small, already-narrowed population, not a huge one.
- Exact (Clopper-Pearson) binomial lower bounds were not computed in this pass (no `scipy` available in this environment's venv this run) — Wilson is a standard, slightly-less-conservative substitute; if the owner wants Clopper-Pearson specifically for the governance record, that's a one-line addition once `scipy` is confirmed available.
- Semantic-type / range-link-subtype stratification (e.g. scoring the 6 unit-basis-flagged and 5 table-required-flagged Queue B records separately from the 26 clean ones) is recommended given this audit found those subgroups behave differently — but the owner, not this audit, should set the actual governance threshold and stratification weights.

**No governance threshold is selected here.** Per the owner's explicit instruction, this section prepares proposals only.

## C7 entry decision (Phase 23)

**READY_FOR_OWNER_REVIEW**

Rationale: Queue A (53 records) and Queue B (43 records) are built, hashed, free of preloaded verdicts, and backed by two independent, evidence-cited audit passes (deterministic re-run + blinded human-equivalent Pass A + byte-level PDF/unit verification). Zero owner review events exist yet (`review_decisions = 0`, confirmed in Phase 0 and re-confirmed unchanged throughout this program — no DB was written). C7 does not activate any type; nothing here changes `TYPES_MEETING_PRECISION_THRESHOLD`, `calculation_eligibility`, or `approved_by`.
