# RC-030 C6 — Span-Linked Attribution: Architecture, Algorithm, and Results Audit

## Module

`dose_verification_sandbox/span_attribution.py` — pure, deterministic, offline text analysis. Imports only `medical_normalizer.dictionary.DRUG_SYNONYMS` (the governed drug-synonym dictionary already used by the production parser) plus Python stdlib (`re`, `unicodedata`, `hashlib`, `json`, `dataclasses`). Zero database, network, filesystem, or Clinical Engine access (grep-verified; regression-tested in `test_span_attribution.py::test_module_has_no_io_or_network_or_clinical_engine_imports`).

## Canonical text model (Part III)

`normalize_text()` performs Unicode NFC normalization, non-breaking-space collapsing, dash-variant unification (‐‑‒–—− → `-`), and whitespace-run collapsing, while building an `offset_map` that traces every normalized-text position back to its exact raw-text offset. No evidentiary character (digit, letter, meaningful punctuation) is ever deleted or substituted — only whitespace/dash/Unicode canonicalization, exactly as required. `normalize_decimal()` is a separate, numeric-comparison-only helper (comma → point) that never mutates stored text.

## Span detection (Part IV)

- **Antibiotic spans** (`find_antibiotic_spans`): matched only against `medical_normalizer.dictionary.DRUG_SYNONYMS` (117 governed aliases) — never inferred from clinical context. An unmatched or absent antibiotic mention correctly yields zero spans rather than a guess.
- **Range spans** (`find_range_spans`): regex `(\d[\d.,]*)\s*-\s*(\d[\d.,]*)\s*(мг/кг/сут|мг/кг/сутки|мг/кг/день|мг/кг|г/сут|г|мг|мл)` — the unit whitelist itself is the primary exclusion mechanism for age/duration/interval ranges (e.g. "3-5 лет" is never matched at all, since "лет" isn't a dose unit). Where a range-shaped number sequence *is* followed by a dose unit but overlaps a `не более`/`максимальн`/`макс. доза` marker, it is explicitly excluded as `MAXIMUM_CLAUSE`. Non-increasing "ranges" (lower ≥ upper) are excluded as malformed.

## Structural boundaries (Part V)

`hard_boundary_between()` checks, between two offsets: alternative separator (`или`), semicolon, sentence-ending period. `phase_marker_between()` checks for loading/maintenance vocabulary (`нагрузочн`, `первая доза`, `стартов`, `затем`, `далее`, `поддерживающ`, `последующ`) between a candidate drug and range.

## Attribution / link scoring (Part V Phase 6-7)

`attribute()` implements exactly the required fail-closed hierarchy:
1. Find all true (non-excluded) range spans and all antibiotic spans.
2. For each true range, find the nearest antibiotic span and score: same-segment (no intervening different-drug antibiotic, no hard boundary), unit match (`_base_unit()` — strict leading-token comparison, e.g. `г` vs `мг` never match as substrings, a real bug found and fixed during testing), scalar match (lower bound equals the regimen's current structured dose), phase conflict.
3. Only ranges passing same-segment + unit-match + no-phase-conflict enter the `valid` set.
4. Zero valid candidates → `WRONG_RANGE_ANCHOR` (or `AMBIGUOUS_LOADING_MAINTENANCE`/`AMBIGUOUS_ALTERNATIVE_BOUNDARY` when the rejection reason indicates one specifically).
5. Multiple valid candidates → `AMBIGUOUS_MULTIPLE_RANGES` unless exactly one also has a scalar match (then that one alone survives).
6. Exactly one valid candidate: `SAFE_EXACT_LINK` only when there is exactly one distinct drug in the whole text AND both scalar and unit match; `SAFE_SINGLE_CANDIDATE` when scalar+unit match but multiple drugs are present in the text without conflict; otherwise `AMBIGUOUS_MULTIPLE_DRUGS`.

No clinical plausibility, no "common dosing knowledge," no AI voting anywhere in this function — confirmed by source inspection (the function contains no AI/ML call, no external knowledge lookup beyond the governed dictionary).

## Table recovery (Part VI) — NOT executed, disclosed

As recorded in `RC030_C6_BASELINE.md`, no local PDF corpus exists in this environment. Records whose `source_quote` looks table-derived (heuristic: >3 newlines and >20 digit characters) are passed with `table_context=True`, which short-circuits `attribute()` straight to `AMBIGUOUS_TABLE_CONTEXT` with an explicit `table_recovery_unavailable_in_this_environment` reason — never a guessed table link. 12 of 179 records fell into this bucket.

## Real execution against the 179 SUSPECT records (Part IX)

Run via a one-off script (not committed — see `RC030_C6_EXACT_ALLOWLIST.md`) against `source_quote`, `antibiotic`, `dose`, `unit` pulled directly from `assembled_regimens.sqlite` for all 179 real SUSPECT `regimen_id`s (identified from the existing 365-row manifest's `range_attribution_trust == "SUSPECT_MULTI_DRUG_QUOTE"` rows — the same real set C3/prior turns already established). Results:

| Classification | Count |
|---|---|
| `WRONG_RANGE_ANCHOR` | 111 |
| `AMBIGUOUS_ALTERNATIVE_BOUNDARY` | 23 |
| `AMBIGUOUS_TABLE_CONTEXT` | 12 |
| `NOT_A_DOSE_RANGE` | 22 |
| `AMBIGUOUS_MULTIPLE_DRUGS` | 10 |
| `AMBIGUOUS_LOADING_MAINTENANCE` | 1 |
| `SAFE_EXACT_LINK` / `SAFE_TABLE_LINK` / `SAFE_SINGLE_CANDIDATE` | **0** |

**Zero of the 179 SUSPECT records reach a SAFE classification.** This is a real, honest result, not a shortfall of the implementation — spot-checking three `WRONG_RANGE_ANCHOR` records against their actual `source_quote` text confirms the engine is behaving correctly:

- **Regimen 5584**: the structured dose (1.0 g) has *three* candidate numeric spans in the quote corresponding to three different surgical-timing phases (pre-operative single dose, intra-operative range, post-operative q8h range) for the *same* drug — genuinely multi-phase, and the engine correctly refuses to pick one.
- **Regimen 5622**: the structured drug is Vancomycin at a scalar 15 mg/kg (no range in the text at all for Vancomycin); the only numeric range in the quote (0.6-0.9 g) belongs to Clindamycin, introduced after "Или" (Or) as a fully separate alternative drug. This is **exactly** the "wrong-drug first range" failure mode this engine exists to prevent — correctly rejected.
- **Regimen 5624**: a combined "Цефазолин + Метронидазол" regimen where Цефазолин's dose text is malformed (`1,0-2,0-3,0 г`, three numbers not a clean range) and Метронидазол has its own separate range — genuinely ambiguous multi-drug text, correctly not linked.

Because the 179 SUSPECT set was *already* selected (in a prior turn) as precisely the subset where the naive heuristic's first-range guess **disagreed** with the structured scalar, it is disproportionately weighted toward multi-phase, multi-drug, and alternative-boundary text — the hardest cases by construction. A 0% safe-link rate on this specific adversarial subset is a defensible, conservative outcome, not evidence of a broken engine (the spot-checks above and the 30-test unit suite, including deliberately adversarial multi-drug/boundary fixtures, all pass).

## Known limitation (documented, not silently hidden)

The `WRONG_RANGE_ANCHOR` catch-all (111/179) conflates several distinct rejection reasons (no valid segment, generic boundary mismatch) that a richer phase-marker vocabulary could sub-classify more precisely — e.g., regimen 5584's perioperative timing language ("во время операции", "после операции") isn't recognized by the current `_LOADING_MARKER_RE`, which is tuned to "нагрузочная"/"поддерживающая" vocabulary instead. Expanding this vocabulary is a deferred refinement (Phase 15 category F equivalent), not a safety defect — the safety property that matters (never a wrongly-confident SAFE link) holds regardless of which specific `AMBIGUOUS_*`/`WRONG_RANGE_ANCHOR` label a given non-safe case receives.

## Determinism

`canonical_result_hash()` produces a stable SHA-256 over classification + selected span offsets/values, excluding nothing time-dependent (the module has no timestamps). Regression-tested: repeated calls on identical input produce identical hashes; the full 179-record run only reads `assembled_regimens.sqlite` (never writes) and was executed via a read-only script, not committed to git (see allowlist).
