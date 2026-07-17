# RC-030 C6.1 — Exact Path Allowlist (Phase 19)

Frozen allowlist. Nothing outside this list is staged. No directory/wildcard staging.

## C61-CODE (one proven deterministic engine fix)

| Path | Size (bytes) | SHA-256 | Reason |
|---|---|---|---|
| `dose_verification_sandbox/span_attribution.py` | 18328 | `29150660098da37014680268847f59eeded56d26a6dd9dc328d6120e8264f340` | Adds `DICTIONARY_GAP`/`ENGINE_REVIEW_REQUIRED` classifications; fixes the zero-antibiotic-span case, previously mislabeled `AMBIGUOUS_MULTIPLE_DRUGS` (which implies competing drugs were detected, when in fact none were) — a real defect found in this turn's dictionary-coverage audit, affecting 40/365 real records (33 of them former-`TRUSTWORTHY`). Proven safe: the change only relabels a non-SAFE outcome to a more accurate non-SAFE label; no record moves into or out of `SAFE_EXACT_LINK`/`SAFE_TABLE_LINK`/`SAFE_SINGLE_CANDIDATE` as a result (verified: before/after 365-record replay both show 0 SAFE). |

## C61-TESTS

| Path | Size (bytes) | SHA-256 |
|---|---|---|
| `tests/dose_verification_sandbox/test_span_attribution.py` | 15851 | `5dac4db85b7dcab6cb2f40725a9364c92a32b966ea65e4af2835bbb813a67f74` |

6 new tests added this turn (36 total in the file): the `DICTIONARY_GAP` regression (the exact defect above), a "dictionary gap is never safe" guard, a coincidental-scalar-match-with-multiple-drugs adversarial case, a range-before-antibiotic ordering case, a parenthetical-alternative case, and an aggregate adversarial-pattern regression covering the real multi-phase and wrong-drug-after-"или" examples found in the 365-record replay.

## C61-MANIFEST (compact, aggregate/governance-metadata only)

| Path | Size (bytes) | SHA-256 | Reason |
|---|---|---|---|
| `RC030_C61_BASELINE.json` | 1094 | `395814198ee8ce883c836f8e1ee8cbef5432d40606b7c5f4e99cf7e9a373cace` | Compact baseline facts. |
| `RC030_C61_RANGE_REVALIDATION_SUMMARY.json` | 1041 | `220a2531d9c8ab05cc4fee1c3390604e33bf2f5207682ac7d5743a49267fc1c2` | Aggregate classification counts, trust-retained/revoked counts, engine hashes before/after. No per-record source quotes. |
| `RC030_C61_OWNER_REVIEW_QUEUE.json` | 28145 | `e46f01b078f0931d6e1ed1f9814922a46170de656e3878104d1fecf99dfe48ec` | 85 items — `regimen_id`/`regimen_version`/`classification`/`old_trust`/governance flags only. No source quotes, no offsets, no preselected verdict. |

## C61-DOCS

| Path | Size (bytes) | SHA-256 |
|---|---|---|
| `RC030_C61_BASELINE.md` | 2628 | `b4d374de9953e59c8393a3c103c800a4d0dda4569921d084a5fe38a55f4f58d0` |
| `RC030_C61_ROOT_CAUSE_REPORT.md` | 5913 | `bbc3704deffca1dbafc2cbc5a8acf73e95282eb891f5efc3ff44ef3828849f6a` |
| `RC030_C61_MIGRATION_READINESS_REPORT.md` | 3719 | `c84bce78138d2aa0a11cb104fd9c57610ff72d58fbd0dec2a829acd82658ff2c` |
| `RC030_C61_EXACT_ALLOWLIST.md` | (this file) | — |
| `RC030_C61_PRESTAGING_AUDIT.md` | written next | — |
| `RC030_C61_COMPLETE_RANGE_REVALIDATION_REPORT.md` | written next | — |

## Explicitly excluded (with reason)

| Path | Reason |
|---|---|
| `generated/rc030_c61/pass_a_365.json` | Full 365-record Pass A result (pre-`DICTIONARY_GAP`-fix run) — superseded scratch output. |
| `generated/rc030_c61/range_revalidation_365.json` | Full 365-record final result dump including per-record source hashes/offsets/old-trust cross-reference — generated clinical evidence, excluded per the same data-minimization policy as C3/C6. |
| `RC030_RANGE_REPROCESS_MANIFEST.json` (pre-existing) | Unchanged, still excluded (304 KB full 365-row manifest with source quotes). |
| Any SQLite | None created this turn — no `generated/rc030_c61/*.sqlite` was built (0 SAFE rows means nothing to populate beyond an unchanged copy; same reasoning as C6). |
| One-off processing scripts | Run inline via the shell (never saved as repository files). |
| C1-C6 code other than `span_attribution.py` | Untouched — verified via `git status --short`. |
| Clinical Engine | Untouched. |

## Totals

- 1 code file (1 deterministic fix) + 1 test file (6 new tests) + 3 manifest files + up to 6 doc files = 11 tracked paths
- 0 SQLite, 0 PDF, 0 full clinical-evidence dump, 0 owner export, 0 AI event store
