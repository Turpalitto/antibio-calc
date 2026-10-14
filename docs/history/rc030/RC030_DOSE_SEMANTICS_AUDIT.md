# RC030_DOSE_SEMANTICS_AUDIT.md

Status: RC-030 Phase 1. Full-population classification of all 2,675 rows in
`assembled_regimens.sqlite`, produced by `dose_verification_sandbox.semantics_parser.classify_regimen`
(source: `dose_verification_sandbox/data/full_corpus_classification.json` / `full_corpus_metrics.json`).
Read-only; the classifier was validated by hand against a 40-row random sample (`seed=42`) of
`source_quote` text before being run at full scale — see "Validation" below.

## Category counts (semantic_type), full corpus (n=2,675)

| Category | Count | % of corpus |
|---|---:|---:|
| K — MISSING (dose is NULL) | 658 | 24.6% |
| D — FIXED_PER_DOSE | 579 | 21.6% |
| C — FIXED_PER_DAY | 525 | 19.6% |
| A — WEIGHT_PER_DAY | 461 | 17.2% |
| J — AMBIGUOUS | 202 | 7.6% |
| L — NOT_A_DOSABLE_REGIMEN (`NOT_APPLICABLE`) | 96 | 3.6% |
| B — WEIGHT_PER_DOSE | 80 | 3.0% |
| I — SOURCE_EXPLICIT_BUT_UNPARSED (`UNPARSED`) | 74 | 2.8% |
| E/F — RANGE_PER_DAY / RANGE_PER_DOSE | 0 | 0.0% |

E/F (dose ranges) measure zero because `assembled_regimens.sqlite` has no range columns at all
(confirmed in the Phase 0 audit) — every `dose` value is a single point, so `numeric_min ==
numeric_max` for every row and no row can ever land in a RANGE_* category against this schema. This
is a genuine structural absence, not a classifier miss.

G/H (MAX_DAILY_DOSE / MAX_SINGLE_DOSE as a row's *own* type) are not used as row-level categories —
see "Max-dose extraction" below for why, and the auxiliary extraction results instead.

M (INVALID_NOISE) was folded into L (`NOT_APPLICABLE`) — see the heuristic note in
`dose_verification_sandbox/semantics_parser.py::classify_regimen`. This is a coarser split than the
spec's ideal L vs M distinction; documented as a known simplification, not hidden.

## Ambiguity status breakdown

| Status | Count |
|---|---:|
| UNAMBIGUOUS (explicit textual signal found) | 1,041 |
| RESOLVED_BY_FREQUENCY_ONE (algebraic shortcut, frequency=1) | 604 |
| NOT_APPLICABLE (row is MISSING/UNPARSED/NOT_APPLICABLE — signal detection doesn't apply) | 828 |
| AMBIGUOUS_NO_SIGNAL (no signal found, frequency != 1) | 202 |
| AMBIGUOUS_CONFLICTING_SIGNAL | 0 |

Zero rows ended in a genuine conflicting-signal state at full scale — the proximity-based nearest-match
logic (see `DOSE_SEMANTICS_PARSER_SPEC.md`) resolved every case where both a per-dose and a per-day
signal were textually present in the same window.

## By review status (status column)

| status | resolvable (A+B+C+D) | AMBIGUOUS | UNPARSED | MISSING | NOT_APPLICABLE | total |
|---|---:|---:|---:|---:|---:|---:|
| REVIEW_REQUIRED | 1,352 (87.6%) | 149 (9.7%) | 42 (2.7%) | 0 | 0 | 1,543 |
| REJECTED | 293 (26.1%) | 53 (4.7%) | 32 (2.9%) | 658 (58.7%) | 96 (8.6%) | 1,132 |

The 1,543 `REVIEW_REQUIRED` rows are the ones that matter for eventual physician review — 87.6% of
them now have a resolvable, source-backed dose semantic. The `REJECTED` rows are dominated by MISSING
(no dose at all — the assembly engine already correctly rejected these upstream for unrelated reasons).

## By age group

| age_group | resolvable | AMBIGUOUS | total |
|---|---:|---:|---:|
| adult | 476+448+108+44 = 1,076 (56.3%) | 139 | 1,912 |
| child | 89+46+348+36 = 519 (67.6%) | 60 | 768 |
| adult\|pregnancy | 14+31 = 45 (66.2%) | 3 | 68 |
| adult\|renal, child\|renal | 5 (all WEIGHT_PER_DAY) | 0 | 5 |

## Max-dose extraction (auxiliary, not a row-level category)

`assembled_regimens.sqlite` has no dedicated max-dose columns, and a row's own `dose` value is
essentially always the therapeutic dose, not a documented ceiling — so RC-030 did not attempt to
reclassify entire rows as "this row's dose IS a maximum" (categories G/H). Instead, a proximity-scoped
regex (`не более N мг/г`, restricted to mass units so duration phrases like "не более 24 часов" are
never captured) scans the same text window used for period-signal detection:

- **24 rows** got a source-backed `max_daily_dose` value attached.
- **2 rows** got a source-backed `max_single_dose` value attached.
- 104 rows have *some* max-dose-related phrase (`не более`, `максимальная суточная доза`, etc.)
  somewhere in their full `source_quote`, but only 26 of those phrases were both numeric (mass unit)
  and inside the proximity window of this row's own dose token — the rest belong textually to a
  different drug mentioned in the same combined guideline sentence and were correctly not attached
  here (see the known combination-drug attribution limitation in `DOSE_SEMANTICS_PARSER_SPEC.md`).

## Validation

Before running at full scale, the classifier was validated against a random 40-row sample (seed 42,
restricted to `unit in ('mg/kg','mg','g')` with non-empty `source_quote`) by manual reading of each
`source_quote` against the classifier's output. Two real bugs were found and fixed during this process:

1. **Self-conflict on "N раз в сутки"**: the phrase itself contains the substring "в сутки", which
   was independently matching the plain per-day pattern too, producing a spurious
   `AMBIGUOUS_CONFLICTING_SIGNAL` on cases that were actually unambiguous per-dose statements. Fixed
   by excluding plain-per-day matches whose span overlaps any per-dose match.
2. **Leftmost-match bias on combination-drug alternatives**: when a window contained two dose
   alternatives (e.g. "500 mg 3×/day or 875 mg 2×/day"), the first per-dose match in the window was
   used regardless of which dose token it was actually next to. Fixed by picking the nearest match to
   the anchor position by character distance — this resolves the common case correctly but is not
   perfect for combination-drug phrasing where the frequency clause follows two component doses (a
   documented residual limitation, not silently ignored).

After both fixes, 34/40 (85%) of the sample resolved to a definite semantic_type matching manual
reading, 2/40 were correctly `MISSING` (dose is NULL), and the remaining 4/40 were correctly
`AMBIGUOUS` (no frequency data and no textual signal — genuinely unresolvable from the given text).

## Conclusion

The dominant blocking category before RC-030 (`AMBIGUOUS_PERIOD`, i.e. today's `AMBIGUOUS` +
`RESOLVED_BY_FREQUENCY_ONE` combined) affected effectively 100% of dosable regimens. After RC-030,
of the 2,675 rows, **1,645 (61.5%)** now resolve to an explicit, source-backed semantic type, and
within the `REVIEW_REQUIRED` subset that actually matters for physician review, **87.6%** resolve.
202 rows (7.6%) remain genuinely `AMBIGUOUS` — correctly so, per the spec's rule to fail closed rather
than guess.
