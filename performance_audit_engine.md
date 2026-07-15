# Performance Audit — Clinical Decision Engine (full pipeline, real data)

> Measurement only. No code optimized. AUTO_GENERATED report.

## Setup
- SQLite (normalized_regimens): `C:\clinrec_downloader\normalized_regimens.sqlite` — 2675 regimens
- diagnosis_index: `C:\ANTIBIO\clinical_engine\resources\diagnosis_index.json` (AUTO_GENERATED_DRAFT, 895 entries / 294 guidelines)
- drug reference: `C:\ANTIBIO\db\index.json`
- clinical constants: `C:\ANTIBIO\clinical_engine\resources\clinical_constants.json`
- ValidationPolicy: **strict** (production default — PASS-only)
- Workload: 736 unique diagnosis names, full pipeline per query
- Python: 3.12 · single process · no query-level cache (v1)

## Engine.__init__ (reader load, one-time)
- **28.4 ms** — target §9.1 <100ms → **PASS**
- RSS before / after init: n/a (psutil not installed) / n/a (psutil not installed)

## Latency — Workload A (adult, age 45)
| metric | value | target §9.1 |
|---|---:|---|
| P50 | 2.006 ms | — |
| P95 | 7.987 ms | — |
| P99 | 8.925 ms | — |
| max | 14.634 ms | recommend() <50ms → PASS |
| mean | 2.639 ms | — |
| queries/sec | 379 | — |
| recommendations/sec | 2542 | — |
| matched queries | 457/736 | — |
| total accepted / excluded | 4937 / 2402 | — |

## Latency — Workload B (heavy: allergy + 2 current meds + GFR 25 + hepatic)
| metric | value |
|---|---:|
| P50 | 2.200 ms |
| P95 | 8.795 ms |
| P99 | 10.459 ms |
| max | 17.389 ms |
| mean | 2.885 ms |
| queries/sec | 347 |
| recommendations/sec | 2183 |
| total accepted / excluded | 4636 / 2703 |

## SQL query count (per recommend())
- Workload A: total 906, mean 1.23/call, max 5/call
- Workload B: total 906, mean 1.23/call, max 5/call
- One `load_by_guideline` SELECT per matched guideline_id; drug/diagnosis/constants readers are in-memory (0 SQL after init).

## Memory
- Python tracemalloc peak (during workload): 2.2 MB
- Process RSS after full run: n/a (psutil not installed)

## Cache
- v1 has **no query-level cache** (documented — EngineCache is a stub, §9.2.5).
- Readers loaded **once** at `Engine.__init__`; all subsequent drug/diagnosis/
  constants access is in-memory dict O(1) → effective "hit rate" 100% in-memory,
  0 re-reads. SQLite connection reused across all queries (no reopen).

## Bottleneck analysis — per-stage mean (Workload B, heaviest)
| Stage | mean ms/call | % of pipeline |
|---|---:|---:|
| DiagnosisMatch | 0.0085 | 0.3% |
| RegimenLoad | 1.8719 | 69.1% |
| PopulationFilter | 0.0191 | 0.7% |
| TherapyLineSelect | 0.0066 | 0.2% |
| HardSafetyFilter | 0.1356 | 5.0% |
| DoseCalculation | 0.1181 | 4.4% |
| DoseAdjustment | 0.1707 | 6.3% |
| InteractionCheck | 0.0742 | 2.7% |
| RankRecommendations | 0.1821 | 6.7% |
| Trace | 0.1225 | 4.5% |

## Notes
- STRICT policy loads PASS-only (1039 of 2675) — worst-case candidate fan-in
  per guideline is small (≤ tens of rows), so latency is dominated by fixed
  per-stage overhead, not data volume.
- diagnosis_index is a DRAFT (895 entries, 101 conflicting diagnosis→guideline
  mappings). Conflicts inflate candidate counts for ambiguous diagnoses (a
  lookup may fan out to multiple guidelines) — see build_diagnosis_index_draft
  report. This is a data-quality caveat, not an engine perf issue.
