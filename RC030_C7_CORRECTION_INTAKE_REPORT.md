# RC-030 C7 Correction Intake Report

Date: 2026-07-30

## Final closure: repaired 6068

Validated
`rc030_owner_review_c5_range-single-review_export_2026-07-30T06-40-10-025Z.json`
(SHA-256
`B4FD86F3AD7FC86F56F25B1024D843320AB16CD8ABCEDF9E63DE7ED0496BE5F0`).
It contains 25 events across 15 single-mode regimens with zero validation
issues. The new `6068` event uses repaired evidence identity
`dc0778152ff3053db9cdf4cb9d74e6759bb7ea09f27b6497148ccbc94a4886a0`,
supersedes the historical extraction-defect event, and terminates in
`CORRECT_RANGE_SINGLE`.

Final consolidation: 182 events, 113/113 regimens, zero validation issues,
105 exact owner/AI matches, 8 documented per-administration label
equivalents, zero substantive mismatches, and zero quarantined defects.

## Source export

- file:
  `%USERPROFILE%\Downloads\rc030_owner_review_c5_range-unit-basis-review_export_2026-07-30T05-48-17-122Z.json`
- SHA-256:
  `5501995A13AA9406F20381947D6AFA5F438506E3AE2775946D66E5450B267ECF`
- mode: `range-unit-basis-review`
- events: 77 append-only events;
- unique regimens: 43;
- validator issues: 0.

## Required correction results

| Regimen | Terminal verdict in export | Result |
|---:|---|---|
| 7519 | `CORRECT_RANGE_DAILY` | corrected |
| 7629 | `CORRECT_RANGE_DAILY` | corrected |
| 7644 | `CORRECT_RANGE_DAILY` | corrected |
| 5441 | `WRONG_DOSE_ANCHOR` | still requires correction |

The three corrected records each contain a new event that supersedes the
previous event. Record `5441` has only its original event.

This export does not contain correction events for exact-link records `6296`
and `6550`, because they belong to a different review-mode store.

## Remaining owner checks

The later exact-link export
`rc030_owner_review_c5_range-exact-review_export_2026-07-30T06-00-31-485Z.json`
(SHA-256
`65E7570E9DDE179A4E4A42337BAC76F368088F86121D68A504FE42C531DA53A7`)
also passed validation with zero issues. It contains new superseding
`CORRECT_RANGE_SINGLE` verdicts for `6296` and `6550`.

A subsequent repeat export
`rc030_owner_review_c5_range-exact-review_export_2026-07-30T06-03-01-519Z.json`
(SHA-256
`AAA20446333F46B507007561DDB1B99C89A084C7E6AF5311FBE378D61B1BD7CD`)
also passed validation. It adds one more same-verdict superseding event for
each of `6296` and `6550`; their terminal interpretation is unchanged. It
contains no events for `5475` or `5478`.

Five substantive checks remain:

- engine disagreement: `5475`, `5478`;
- unit basis: `5441`;
- single candidate: `5528`, `5824`.

The engine-review export
`rc030_owner_review_c5_range-engine-review_export_2026-07-30T06-12-33-760Z.json`
(SHA-256
`514CC7E66AAFBB47F61ACD2B0F04589E21750F6BDA24A149C97CE049A3A1603F`)
passed validation with zero issues. Terminal verdicts for `5475` and `5478`
are now `CORRECT_RANGE_SINGLE`. Earlier and redundant same-verdict events
remain preserved in their append-only chains.

Three substantive checks now remain: `5441`, `5528`, and `5824`.

The later unit-basis export
`rc030_owner_review_c5_range-unit-basis-review_export_2026-07-30T06-14-15-243Z.json`
(SHA-256
`CD60F407E2F437492BE304E69D4AEC59B38225004D6C328C0B95B33C20A5C0F2`)
passed validation with zero issues. The terminal verdict for `5441` is now
`CORRECT_RANGE_DAILY`; a redundant same-verdict superseding event is
preserved.

Only `5528` and `5824` remain for owner correction.

The single-candidate export
`rc030_owner_review_c5_range-single-review_export_2026-07-30T06-19-37-110Z.json`
(SHA-256
`0C6DD25E9CBF67F2B2CDB2854F3E69C745B2127431FCC86EA79A2B788A7CF893`)
passed validation with zero issues. `5824` now terminates in
`CORRECT_RANGE_SINGLE` and is closed.

`5528` still terminates in `CORRECT_RANGE_SINGLE`, which does not resolve
the wrong-dose-anchor defect: the `15-20 mg/kg` range belongs to ethambutol,
while the target rifabutin dose is `5 mg/kg once daily`. One final owner
correction remains: `WRONG_DOSE_ANCHOR` for `5528`.

The subsequent export
`rc030_owner_review_c5_range-single-review_export_2026-07-30T06-23-52-507Z.json`
(SHA-256
`A57BDFBD261F34D9F981954948765147ECEB1ED86B1E19B69439075FDDD2D71C`)
passed validation with zero issues but added two more
`CORRECT_RANGE_SINGLE` events for `5528`. Therefore the wrong-anchor defect
remains open. A dedicated retry page displays an explicit source comparison
and requires an owner-selected button `4`.

Record `6068` remains quarantined for source repair and is not an owner
correction check at this stage.

## Final correction closure

The final single-mode export
`rc030_owner_review_c5_range-single-review_export_2026-07-30T06-29-18-808Z.json`
(SHA-256
`82E652B5B37C4E93B3E5A496D4461018D3C5668048DF09F93DF6DEBB4C7E8904`)
passed validation with zero issues. Regimen `5528` now terminates in
`WRONG_DOSE_ANCHOR`.

All ten substantive owner/AI disagreements are closed. Consolidation across
the latest five review-mode histories produced 181 events, 113 unique
regimens, zero validator issues, and exactly one terminal event per regimen.
Final comparison: 104 exact matches, 8 table-label equivalents, zero
substantive mismatches, and quarantined extraction defect `6068`.
