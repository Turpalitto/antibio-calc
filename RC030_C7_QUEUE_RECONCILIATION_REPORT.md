# RC-030 / C7 Part II — Queue Reconciliation Report

## Inventory (Phase 1)

All 6 C6.8 queues read directly (no additional generated-directory equivalents found beyond the ones already produced in C6.8 — `generated/rc030_c68/`, `generated/rc030_range_rebuild_v6/` inspected, no separate C5 interface dataset exists yet for C7):

| Queue | File | Schema version | Record count |
|---|---|---|---|
| Exact-link confirmation | `RC030_C68_EXACT_LINK_OWNER_QUEUE.json` | 1 | 36 |
| General single-candidate | `RC030_C68_SINGLE_CANDIDATE_QUEUE.json` | 1 | 15 |
| Unit-basis review | `RC030_C68_UNIT_BASIS_QUEUE.json` | 1 | 43 |
| Source-blocked | `RC030_C68_SOURCE_DEFECT_QUEUE.json` | 1 | 0 |
| Table review | `RC030_C68_TABLE_REVIEW_QUEUE.json` | 1 | 8 |
| Engine disagreement | `RC030_C68_ENGINE_REVIEW_QUEUE.json` | 1 | 11 |
| **Raw total** | | | **113** |

Every record already carries `evidence_hash`, `pdf_hash`, `source_pdf`/`page`/`quote`, `calculation_eligibility: BLOCKED`, `clinically_approved: false`, `authoritative_migration_allowed: false`. Absence of owner verdict and AI event data reconfirmed by direct key-scan (0 forbidden keys across all 6 files).

## Deduplication (Phase 2)

**No identity key (`regimen_id`, `regimen_version`) appears in more than one C6.8 queue** — the queues were built disjointly by construction in C6.8 (`generated/rc030_c68/build_queues.py` routes each of the 117 candidates into exactly one bucket). Verified programmatically: raw total 113, unique `(regimen_id, regimen_version)` keys 113, **0 duplicate appearances**.

No separate `validation_unit_id` scheme exists upstream of this program — `evidence_hash` (sha256 of `regimen_id`/`version`/`source_pdf`/`page`/`source_quote`) is used as the authoritative per-record identity, per the fallback key the spec allows ("regimen ID + regimen version + source packet hash + semantic claim"). All 113 `evidence_hash` values independently confirmed unique.

## Supplemental tagging

Beyond each record's primary C6.8 queue category, the finer-grained C6.7 single-candidate disposition reasons (`RC030_C67_SINGLE_CANDIDATE_DISPOSITION.md`) were checked for two additional tags the spec names (`PHASE_REVIEW`, `ALTERNATIVE_REVIEW`, `MAXIMUM_CONFLICT`):

| regimen_id | C6.7 disposition | Supplemental tag | Landed? |
|---|---|---|---|
| 5726 | `SINGLE_REQUIRES_PHASE_SPLIT` | `PHASE_REVIEW` | ✅ (now in `GENERAL_SINGLE_CANDIDATE`) |
| 6638 | `SINGLE_REQUIRES_ALTERNATIVE_REVIEW` | `ALTERNATIVE_REVIEW` | ✅ (now in `UNIT_BASIS_REVIEW`) |
| 5514 | `SINGLE_REQUIRES_ALTERNATIVE_REVIEW` | `ALTERNATIVE_REVIEW` | ❌ — no longer in any C6.8 queue (rejected, `WRONG_RANGE_ANCHOR`, by the C6.8 basis repair) |
| 5526 | `SINGLE_WRONG_ANCHOR` | `MAXIMUM_CONFLICT` | ❌ — same reason |
| 5533 | `SINGLE_WRONG_ANCHOR` | `MAXIMUM_CONFLICT` | ❌ — same reason |

No new owner task was created by this tagging pass — a record with two tags still has exactly one master-registry entry.

## Final counts

- Raw queue total: **113**
- Unique validation units: **113**
- Duplicate appearances: **0**
- Duplicate groups: **0** (none found)
- Final unique task count: **113**

Full machine-readable registry: `generated/rc030_c7/master_registry.json`.

## Priority order (Phase 3)

Deterministic, assigned by queue category, no AI-confidence-based reordering:

| Priority | Category | Count |
|---|---|---|
| 1 | `EXACT_LINK_CONFIRMATION` | 36 |
| 2 | `ENGINE_DISAGREEMENT` + `UNIT_BASIS_REVIEW` | 11 + 43 = 54 |
| 3 | `TABLE_REVIEW` | 8 |
| 4 | `GENERAL_SINGLE_CANDIDATE` + `SOURCE_BLOCKED` | 15 + 0 = 15 |
| **Total** | | **113** |

Within each priority, ordering is `(primary_queue, regimen_id, regimen_version)` — deterministic, reproducible, no randomness. Full ordering: `generated/rc030_c7/master_registry_prioritized.json`.
