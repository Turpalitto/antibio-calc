# RC-030 C6 — Exact Path Allowlist (Phase 24)

Frozen allowlist. Nothing outside this list is staged for C6. No directory/wildcard staging.

## C6-CODE

| Path | Size (bytes) | SHA-256 | Reason |
|---|---|---|---|
| `dose_verification_sandbox/span_attribution.py` | 17709 | `97d30c485643e443fc9e96ddf046a0912844ca1359b400beb4836df22e1a656b` | Deterministic span-linked attribution engine: canonical text model, antibiotic/range span detection, structural boundary rules, fail-closed link scoring, classification taxonomy. Pure text analysis — no DB/network/Clinical Engine access (grep- and test-verified). |

## C6-TESTS

| Path | Size (bytes) | SHA-256 |
|---|---|---|
| `tests/dose_verification_sandbox/test_span_attribution.py` | 11945 | `1229849c5c49ec78278cc49cee33ab37967d4cfc01d0d27597d9c3b3a4825b6c` |

30 tests: normalization, exclusion rules (age/duration/interval/maximum/non-increasing), safe/unsafe attribution (including the exact "wrong-drug first range" adversarial case), boundary detection (alternative/semicolon/sentence), loading/maintenance, table-context honesty, determinism, and the no-I/O/no-Clinical-Engine/threshold-untouched safety regressions.

## C6-MANIFEST

| Path | Size (bytes) | SHA-256 | Reason |
|---|---|---|---|
| `RC030_C6_BASELINE.json` | 1560 | `cfca5de2d993b673705dc2b9755b23a02f26bced59b4926897ba124f8377cf76` | Compact baseline facts — hashes, counts, commit chain. No per-record data. |
| `RC030_C6_V2_V3_COMPARISON.json` | 1056 | `dc3ce65e1e6611239c8bc5245318aa890ea29a224a4199971f81f2505d5c08a2` | Aggregate classification counts only — no per-record source quotes/offsets. |
| `RC030_C6_OWNER_REVIEW_QUEUE.json` | 5895 | `fcbdc3df72a0898bc07498f2dbe83e56149250389c08fb7e3465ee1781db3060` | 23 items (regimen_id + classification + governance flags only) — no source quotes, no preselected verdict, no owner data. |

## C6-DOCS

| Path | Size (bytes) | SHA-256 |
|---|---|---|
| `RC030_C6_BASELINE.md` | 3829 | `9f7309d7dcb8b50c8f099e50ee1184ae5c47844a8cc04da8c3c8eb283f1bff61` |
| `RC030_C6_ARCHITECTURE_AUDIT.md` | 8409 | `cd0b9fa143969be861f6753f01c315776b7af43d2b5e52701c9cfd0908305fa4` |
| `RC030_C6_V2_V3_COMPARISON_REPORT.md` | 2278 | `3c28855685836d2f7a0c991ca0285f026fdcc4472a6adc335912de20e08db61e` |
| `RC030_C6_AUTHORITATIVE_MIGRATION_UPDATE.md` | 4955 | `d8bb428ad2faef520414c535cba5d08984baf5f94cf93a7019f9202855c53d96` |
| `RC030_C6_EXACT_ALLOWLIST.md` | (this file) | — |
| `RC030_C6_PRESTAGING_AUDIT.md` | written next | — |
| `RC030_C6_SPAN_LINKED_RANGE_REPORT.md` | written next | — |

## Explicitly excluded (with reason)

| Path | Reason |
|---|---|
| `generated/rc030_range_rebuild_v3/rederivation_manifest.json` | 123 KB, full 179-record result dump including per-record source offsets and previous-naive-result fields — generated clinical evidence, excluded per Phase 23/Part IV data-minimization discipline (same policy as C3's full 365-row manifest exclusion). |
| `generated/rc030_range_rebuild_v3/RC030_C6_V2_V3_COMPARISON.json` | Duplicate of the committed root-level copy; the `generated/` copy is scratch output, not the tracked source. |
| `RC030_RANGE_REPROCESS_MANIFEST.json` (pre-existing, untracked) | Unchanged from C3's exclusion — still the 304 KB full 365-row manifest, still excluded. |
| Any span-map / evidence-offset dump beyond the compact owner-review queue | Not generated this turn as a separate large file — the full per-record results already live only in the excluded `rederivation_manifest.json`. |
| Any SQLite | None created — Part X (`generated/rc030_range_rebuild_v3/*.sqlite`) was not built this turn (0 SAFE-classified rows means there is nothing to populate a V3 experimental SQLite with beyond byte-identical copies of the authoritative rows — judged not worth the generated-artifact weight for an empty diff; documented as a deferred, not-executed step). |
| One-off processing script | Run inline via the shell (never saved as a repository file) to produce the results above — nothing to stage. |
| C1-C5 code | Untouched — verified via `git status --short`. |
| Clinical Engine | Untouched. |

## Totals

- 1 code file + 1 test file + 3 manifest files + up to 7 doc files = 12 tracked paths
- 0 SQLite, 0 PDF, 0 full clinical-evidence dump, 0 owner export, 0 AI event store
