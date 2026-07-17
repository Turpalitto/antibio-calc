# RC-030 / C6.7 Part X-XI — Owner Review Queues, C5 Modes, AI Pre-Review

## QUEUE A — exact-link confirmation

[RC030_C67_EXACT_LINK_OWNER_QUEUE.json](RC030_C67_EXACT_LINK_OWNER_QUEUE.json) — **53 records**, exactly the `EXACT_LINK_RETAINED` set from Part V. No preselected verdict, no AI conclusion, no `frozen_classification`/`pass_a_verdict` field present (verified by direct key-scan: 0 forbidden/preloaded keys leaked across all 53 records). Each record carries `evidence_hash` (unique, sha256 of regimen_id/version/source_pdf/page/quote), `pdf_hash`, and `context_before`/`context_after` (±200 chars around the quote, extracted live from the real PDF page text via the already-tested `pdf_evidence.find_quote_in_page_text`).

## QUEUE B — single-candidate review

[RC030_C67_SINGLE_CANDIDATE_OWNER_QUEUE.json](RC030_C67_SINGLE_CANDIDATE_OWNER_QUEUE.json) — **43 records**, all of them, grouped by `review_reason_group` (the Part VI disposition bucket). Same evidence-hash/no-preload guarantees as Queue A. Every record explicitly carries `calculation_eligibility: "BLOCKED"`, `clinically_approved: false`, `authoritative_migration_allowed: false` — never migration-safe regardless of any future owner confirmation, per the owner's explicit instruction.

Queues are not mixed: 53 + 43 = 96, and the 21 non-retained exact-link records (downgraded/rejected/review-required) appear in **neither** queue — they are not confirmation-ready and are not single-candidates; their disposition is recorded only in [RC030_C67_DOUBLE_PASS_REPORT.md](RC030_C67_DOUBLE_PASS_REPORT.md).

## C5 range-review modes (Phase 17)

**Gap found and fixed:** `generated/rc030_recovery/build_interface.py --mode` previously only accepted `all` or `control` — there was no `range-exact-review` or `range-single-review` mode, despite the spec requiring them. Added both as first-class CLI choices plus dedicated (non-generic) owner-facing banner text in `owner_review_template.html`, distinguishing exact-link confirmation from single-candidate review with the correct safety framing for each ("nothing is migration-ready before you submit" vs. "never migration-safe regardless of outcome").

Verified, not assumed:
- **C4-compatible owner events**: unchanged — the template's `UI_ACTION_TO_CANONICAL` mirror and Python `verdict_taxonomy.UI_ACTION_TO_CANONICAL` were not touched by this change.
- **`reviewer_id` fixed to `OWNER_LOCAL`**: unchanged (enforced by `owner_fidelity_events.py`, not touched).
- **No verdict preselection**: confirmed — `build_interface.py` already refuses to build if the dataset contains `owner_verdict`/`canonical_verdict`/`ui_action`/`human_fidelity_verdict`; both new queue files were built with 0 such keys.
- **PDF page shown / evidence highlighted neutrally**: unchanged template behavior, applies identically regardless of mode.
- **Isolated localStorage keys**: the `STORE_KEY`/`CURRENT_IDX_KEY` JS template literals are already parametrized by `${MODE}` generically — the two new mode strings automatically get their own isolated keys with no template change required beyond the banner text; verified by test.
- **Deterministic export, no owner data committed**: unchanged.

Tests added: `tests/rc030_owner_interface/test_c5_owner_interface.py` — 5 new tests (`test_range_review_modes_are_accepted_by_the_builder` ×2 modes, `test_unknown_mode_is_rejected_by_the_builder`, `test_range_review_modes_get_a_distinct_non_generic_banner` ×2 modes, `test_range_review_modes_get_isolated_storage_keys` ×2 modes). **Full suite: 31/31 passing** (26 pre-existing + 5 new), 0 regressions.

## Verdict taxonomy sufficiency (Phase 18)

Checked `dose_verification_sandbox/verdict_taxonomy.py` against the required range-review verdict list:

| Required | Present in canonical taxonomy? |
|---|---|
| CORRECT_RANGE_DAILY | ✅ already exists (`CONFIRMING_VERDICTS`) |
| CORRECT_RANGE_SINGLE | ✅ already exists |
| WRONG_DOSE_ANCHOR | ✅ already exists |
| WRONG_ALTERNATIVE | ✅ already exists |
| WRONG_TABLE_ROW | ✅ exists canonically, not yet UI-reachable (documented, intentional) |
| TABLE_CONTEXT_REQUIRED | ✅ already exists |
| REMAINS_AMBIGUOUS | ✅ already exists |
| SOURCE_INCOMPLETE | ✅ already exists |
| SOURCE_CORRUPTED | ✅ already exists |

**The existing taxonomy is sufficient — no expansion applied in this pass.**

One real concern surfaced by this audit, documented but **not acted on**: the unit-normalization audit (Part VIII) found that `_base_unit()`'s leading-token comparison cannot distinguish absolute-dose from per-kilogram-dose text, meaning several queued records have a genuinely *unresolved* dose basis (is the source range daily or per-dose, absolute or per-kg?) that the current `CORRECT_RANGE_DAILY`/`CORRECT_RANGE_SINGLE` choices would force a reviewer to guess at. The owner's spec explicitly names this exact scenario and proposes (but does not pre-authorize) `CORRECT_RANGE_LINK_BASIS_UNRESOLVED` as a possible new verdict. Per the owner's explicit constraint ("do not add it casually... requires architectural justification, C4 migration policy, mapping tests, precision denominator policy, backward compatibility, separate commit"), **no taxonomy change is made here** — this is flagged as a real, evidence-backed candidate for a future dedicated C4 migration commit, not applied unilaterally. In the interim, reviewers facing a genuinely basis-unresolved record in Queue A/B should use `REMAINS_AMBIGUOUS` (already governed, already scorable-excluded) rather than force a false `CORRECT_RANGE_*` claim.

## AI pre-review (Phase 19)

[generated/rc030_c67/ai_pre_review_companion.json](generated/rc030_c67/ai_pre_review_companion.json) — **96 records** (mirrors the 53+43 queued population), built as a **separate file, never merged into either owner-facing queue**. Every record carries `review_origin: "AI_PRE_REVIEW"`, `owner_verified: false`, `clinically_approved: false`, `calculation_eligibility: "BLOCKED"`, and the engine classification / Pass A verdict / confidence / rationale — i.e. exactly the AI conclusions the owner-facing queues must never preload. This file is linkable to a queue record only via `evidence_hash` (present in both), so a reviewer or tool could show it *after* a submission, never before — matching the spec's "may appear only after owner submission" requirement. Not wired into the C5 interface's reveal-after-submit UI in this pass (that would require a template change consuming this companion file — flagged as follow-up, not attempted here since it's a UI feature addition beyond the two-mode gap this turn closed).
