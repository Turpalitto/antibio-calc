# RC-030 C7 — Owner Validation Plan (Phase 27)

This is an **operational proposal**, not a governance decision. No threshold has been owner-approved. All numbers below are proposals, labeled as such.

## Per-semantic-type status (from the C6.5 real 365-record replay)

| Semantic type / classification bucket | Corpus count (of 365 range candidates) | Current strict source-attribution status |
|---|---|---|
| `SAFE_EXACT_LINK` | 74 | Structurally strongest; still `NOT_OWNER_VERIFIED` |
| `SAFE_SINGLE_CANDIDATE` | 43 | Weaker signal by design; always review-required, never migration-equivalent to `SAFE_EXACT_LINK` |
| `AMBIGUOUS_MULTIPLE_DRUGS` | 50 | Requires owner adjudication of which drug the range belongs to |
| `WRONG_RANGE_ANCHOR` | 60 | Requires owner confirmation the range is genuinely unattributable, or further engine improvement |
| `AMBIGUOUS_ALTERNATIVE_BOUNDARY` | 40 | Requires owner adjudication of alternative structure |
| `DICTIONARY_GAP` | 40 | Requires either dictionary curation or context-recovery (partially explored in C6.4) |
| `AMBIGUOUS_TABLE_CONTEXT` | 23 | Requires PDF table-layout recovery (now unblocked at the data-availability level, not yet executed) |
| `NOT_A_DOSE_RANGE` | 26 | Requires confirmation no true range exists |
| `AMBIGUOUS_MULTIPLE_RANGES` | 7 | Requires owner adjudication of which range applies |
| `AMBIGUOUS_LOADING_MAINTENANCE` | 2 | Requires phase-specific splitting |

## Recommended initial review sample (proposal)

Start with the 15-item `SAFE_EXACT_LINK` sample already included in `RC030_C66_OWNER_REVIEW_QUEUE.json` — highest structural confidence, smallest review burden, directly informs whether the unit-normalization fix's output can be trusted at scale before expanding review to the full 74.

## Minimum governed sample (proposal, not owner-approved)

`MIN_SAMPLE_SIZE = 30` is the existing code default (`precision_calculator.py`). This plan proposes ratifying it as the formal governance minimum for any future `TYPES_MEETING_PRECISION_THRESHOLD` decision — 30 is a common rule-of-thumb minimum for a stable binomial proportion estimate, consistent with the Wilson-interval method already implemented, but has not been reviewed or approved by the owner as a clinical-governance threshold specifically for this domain.

## Number of confirming/error cases (proposal, not owner-approved)

Not fixed by this plan — depends on the actual observed precision once real review begins. The Wilson lower bound (already implemented and tested) should be the basis for any activation decision, not the raw point estimate, per `RC030_C7_PRECISION_SIMULATION_REPORT.md`'s confidence-bound scenario.

## Unresolved coverage

Every one of the 291 non-SAFE records (365 − 74 `SAFE_EXACT_LINK`) remains unresolved by definition; `SAFE_SINGLE_CANDIDATE` (43) is intentionally kept out of the "resolved" count per the mission's requirement that it never be treated as migration-equivalent.

## Confidence-bound method options (all labeled as proposals)

- **Exact binomial lower confidence bound** — most conservative, no normal-approximation assumption; recommended for small samples.
- **Wilson lower bound** — already implemented in `precision_calculator.wilson_interval()`; good behavior at small-to-moderate N; this plan's default recommendation for consistency with existing tested code.
- **Bayesian conservative bound** (e.g. Jeffreys interval) — not implemented; would require new code and tests if selected.

**No method is ratified by this document.** The owner should select one before any real threshold decision.

## Review priority (proposal)

1. `SAFE_EXACT_LINK` sample (validate the unit-fix's real-world reliability).
2. `SAFE_SINGLE_CANDIDATE` (weaker signal, second priority).
3. `DICTIONARY_GAP` (most directly actionable — many already resolve with wider context per C6.4).
4. `AMBIGUOUS_TABLE_CONTEXT` (blocked on table-layout recovery work, not yet started).
5. Remaining `AMBIGUOUS_*`/`WRONG_RANGE_ANCHOR`/`NOT_A_DOSE_RANGE` — lowest priority, largest volume, most likely to remain genuinely unresolved.

## Source/PDF dependency

`SAFE_EXACT_LINK`/`SAFE_SINGLE_CANDIDATE` results were derived from `source_quote` text (with bounded context expansion for `DICTIONARY_GAP` cases) — no table-layout PDF work was required for these. `AMBIGUOUS_TABLE_CONTEXT` (23 records) is the only category directly blocked on PDF table recovery specifically (Part V, not attempted this turn despite the corpus now being confirmed available).

## No universal statistical threshold is fabricated here

This plan deliberately does not assert a single "the precision must be ≥ X%" number — that is a clinical-governance decision requiring the owner's (and likely a physician's) judgment about acceptable risk, not something to be invented by this document.
