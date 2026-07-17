# RC-030 C6 — Baseline (Phase 0)

## HEAD / branch

- HEAD before C6 work: `863f981842521fa860e50ea4fd2dd0bfc11e57b8` (C5 portability fix)
- Branch: `main`
- Chain: C5-fix (`863f981`) → C5 (`ed5d863`) → C4 (`c41efb5`) → C3 (`d79bb3c`) → C2 (`35d432e`) → C1 (`aa75331`)

## Staging area / tracked files

`git status --short` shows zero `M`/`MM`/`AM` entries for any C1-C5 tracked file. **Staging area empty, C1-C5 clean: PASS.**

## Source DB hashes (re-verified at start of C6)

| Database | SHA-256 |
|---|---|
| `assembled_regimens.sqlite` | `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9` |
| `kb_final.db` | `16c31fba2ecafbb9d6bf7c5bc54afee5b46e41d6088cc0ac10492c852abd67dd` |
| `review_workbench_p56.sqlite` | `3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29` |

All three match the baseline recorded at C1-C5. **PASS.**

## Existing experimental artifacts (untracked, from prior turns)

- `RC030_RANGE_REPROCESS_MANIFEST.json` — 304 KB, 365 rows, sha256 `6797810d4e5ccbe0ff457227b2878cad8d85a58181196cb9be1b5996da2fe239`
- `RC030_RANGE_REPROCESS_MANIFEST_SUMMARY.json` — the C3-committed compact version (365 total, 186 trustworthy, 179 suspect)

## Exact 179 SUSPECT regimen IDs

Extracted from `RC030_RANGE_REPROCESS_MANIFEST.json` where `range_attribution_trust == "SUSPECT_MULTI_DRUG_QUOTE"`: 179 distinct `assembled_regimen_id` values, ranging from 5351 to 7817 (full list stored in the excluded full manifest; not reproduced here per Phase 4 clinical-data-minimization discipline — only counts and the processing pipeline are governed content).

## Normalizer / parser version

`normalizer_version: "RC030-repair-phase9"` (unchanged since C2), `parser_hash` unchanged since C1/C2 verification.

## Safety state (directly measured)

- Assembled rows: 2675
- Calculation eligible: 0
- Approved objects: 0
- `TYPES_MEETING_PRECISION_THRESHOLD`: `set()`
- `review_decisions`: 0
- `review_tasks`: 9153, all `PENDING`
- Clinical Engine: disconnected

## Critical environmental constraint (discovered during this turn's inventory, affects Part VI scope)

`C:\clinrec_downloader` — the path referenced throughout prior RC-030 reports as the local PDF source-storage root — **resolves to the repository root (`C:\ANTIBIO`) in this environment**, not to a PDF archive. No local PDF corpus is present anywhere in this worktree or on this machine. This means:

- **Part VI (table-specific PDF recovery via DocLayout-YOLO/Table Transformer/PyMuPDF page clipping/MinerU/Docling/RapidTable) cannot be genuinely executed in this turn.** Attempting to fabricate table-recovery results without real PDF pages would produce false claims about clinical source evidence — not acceptable for fail-closed clinical governance.
- The attribution engine instead operates on `source_quote` — the short text excerpt already extracted and stored per-regimen in `assembled_regimens.sqlite`. This is the **same source text the original naive "first range" heuristic operated on**, so this turn's engine is a genuine, apples-to-apples improvement in *how* that existing text is analyzed (span-linked vs. naive-first-match), not a claim of access to new source material.
- Records whose source text appears table-derived (heuristically: multi-line, numerically dense) are classified `AMBIGUOUS_TABLE_CONTEXT` rather than guessed at — honest refusal, not a fabricated table-recovery result.

This constraint is recorded here explicitly so every downstream document and the final verdict account for it truthfully.

## Result

All Phase 0 preconditions hold. Proceeding with span-linked attribution built and run against real `source_quote` text for all 179 real SUSPECT records (Parts III-IX), with Part VI (table PDF recovery) explicitly and honestly deferred per the constraint above.
