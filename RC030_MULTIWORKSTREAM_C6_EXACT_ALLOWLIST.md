# RC-030 Multi-Workstream Program — C6.2-C6.6 Exact Allowlist

Frozen allowlist for the combined C6.2 (dictionary)/C6.3 (PDF discovery)/C6.4 (enhanced replay)/C6.5 (structural analysis + engine fixes)/C6.6 (owner queue + C5 compatibility) commit. No directory/wildcard staging.

## C61-CODE (two proven, tested, minimal deterministic engine fixes)

| Path | Size (bytes) | SHA-256 | Reason |
|---|---|---|---|
| `dose_verification_sandbox/span_attribution.py` | 20159 | `c253b30833bb9a1b6ec74487c007adc3b55c499def76305795c86e3e8800a16c` | Two fixes: (1) diagnostic `rejection_reasons` `or`-chain bug (always reported "phase_conflict" regardless of true cause — never affected actual classification decisions, only the informational reason list); (2) `_base_unit()` now canonicalizes script via the already-governed `UnitNormalizer` before comparison, fixing a Latin-vs-Cyrillic unit mismatch that caused 182/223 real records to be wrongly rejected on a superficial script difference. Both fixes proven safe: all 37 pre-existing tests pass, 3 known adversarial real records re-verified to remain correctly non-SAFE, 5 new `SAFE_EXACT_LINK` results manually verified against real source text. |
| `dose_verification_sandbox/pdf_evidence.py` | 2881 | `1a9a6ab63801aeb3291de7d4edeb83a080d44e1879b0b7b7d638f85f09cf2d0e` | New read-only PDF-evidence helper module (C6.3-tools category): locates a stored `source_quote` inside PDF-extracted page text (whitespace-tolerant, fixing a real quote-location bug found during development) and computes a bounded deterministic context window. Never opens a PDF itself — callers supply extracted text. |

## C61-TESTS

| Path | Size (bytes) | SHA-256 |
|---|---|---|
| `tests/dose_verification_sandbox/test_span_attribution.py` | 16933 | `606cf12447ddc34ac89abb28838f8aa2cf3e96e7e98a14a8762df36632f31bde` |
| `tests/dose_verification_sandbox/test_pdf_evidence.py` | 3526 | `a76cba941959cb430903426ed1f2fe6eaad7729bb8faa4d8c1fdf26d4cc61dd0` |

2 new tests added to `test_span_attribution.py` this turn (37 total): the unit-mismatch-reason regression and a general reason-accuracy check. `test_pdf_evidence.py` is entirely new (10 tests).

## C61-MANIFEST (compact, aggregate/governance-metadata only)

| Path | Size (bytes) | SHA-256 | Reason |
|---|---|---|---|
| `RC030_MULTIWORKSTREAM_BASELINE.json` | 2192 | `2d22416e211dd85e37e0bc73e5e903f600fbb81b18b5e8341638712d932a24cc` | Compact baseline facts, hashes, counts. |
| `RC030_C64_ENHANCED_REPLAY_SUMMARY.json` | 1802 | `84c4935f29ad1bdace27969b90a7ebc29426e5d56f4cb282b239ba189f6f2a61` | Aggregate before/after classification counts, PDF-discovery counts, V4 integrity summary. No source quotes. |
| `RC030_C66_OWNER_REVIEW_QUEUE.json` | 40496 | `3ad7b6127b060f8828f320e74e296df3f1823a19d0a4058aa43cb74a185ae502` | 123 items — `regimen_id`/`regimen_version`/`classification`/`old_trust`/governance flags only. No source quotes, no PDF paths, no preselected verdict. |

## C61-DOCS

| Path |
|---|
| `RC030_MULTIWORKSTREAM_BASELINE.md` (3877 bytes, sha256 `9e9c7aea098ca4c2f8609e0e73b12e51156df893db2b2cfb7ca79a63e6e4c93a` — corrected during prestaging audit: removed a literal machine-username path found in the toolchain section, see prestaging audit) |
| `RC030_C62_C63_C64_DICTIONARY_PDF_REPLAY_REPORT.md` |
| `RC030_C65_STRUCTURAL_ANALYSIS_AND_V4_REPORT.md` |
| `RC030_C66_OWNER_REVIEW_QUEUE_AND_C5_COMPATIBILITY_REPORT.md` |
| `RC030_MULTIWORKSTREAM_C6_EXACT_ALLOWLIST.md` (this file) |
| `RC030_MULTIWORKSTREAM_C6_PRESTAGING_AUDIT.md` (written next) |

## Explicitly excluded (with reason)

| Path | Reason |
|---|---|
| `generated/rc030_multiworkstream/master_365_reconciliation.json` | Full 365-record PDF-discovery result with per-record paths — generated evidence, excluded per established policy |
| `generated/rc030_multiworkstream/enhanced_evidence_365.json` | Full 365-record extracted PDF page text — large generated clinical evidence, excluded |
| `generated/rc030_multiworkstream/context_expansion_comparison.json` | Full per-record before/after comparison with classification detail — generated evidence, excluded (aggregate captured in the compact summary above) |
| `generated/rc030_multiworkstream/dictionary_gap_audit_raw.json` | Per-record expected-antibiotic and quote excerpts — generated clinical evidence, excluded |
| `generated/rc030_multiworkstream/replay_with_unit_fix_365.json` | Full 365-record final replay result — generated evidence, excluded |
| `generated/rc030_multiworkstream/c5_range_review_bundle.json` | 66-record C5-compatible bundle with real source quotes — generated evidence, excluded (used only to verify C5 compatibility, not for owner use) |
| `generated/rc030_range_rebuild_v4/assembled_regimens_range_v4.sqlite` | Experimental SQLite artifact — excluded per the same policy as V2/V3 |
| `generated/rc030_c61/*.json` (from the prior C6.1 turn) | Unchanged, still excluded |
| One-off processing scripts | Run inline via the shell; never saved as repository files |
| C1-C6.1 code other than `span_attribution.py` | Untouched — verified via `git status --short` |
| Clinical Engine | Untouched |
| C5 core files | Untouched — compatibility was verified without any modification (see `RC030_C66_...md`) |

## Totals

- 2 code files (2 proven fixes + 1 new module) + 2 test files (12 new tests) + 3 manifest files + 5 doc files = 12 tracked paths
- 0 SQLite, 0 PDF, 0 full clinical-evidence dump, 0 owner export, 0 AI event store
