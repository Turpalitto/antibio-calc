# RC-030 C6.1 — Baseline (Phase 0)

## HEAD / parent / chain

- HEAD: `6e27cebbfd5ccce5973ab4ee19e9f62c56d37c64` (C6)
- Parent: `863f981842521fa860e50ea4fd2dd0bfc11e57b8` (C5 portability fix)
- Chain: C6 → C5-fix → C5 (`ed5d863`) → C4 (`c41efb5`) → C3 (`d79bb3c`) → C2 (`35d432e`) → C1 (`aa75331`)
- `git status --short`: 103 untracked entries, zero tracked modifications. **C1-C6 clean: PASS.**

## Engine identity (must be unchanged for this replay to be a valid "same engine, more input" test)

- `dose_verification_sandbox/span_attribution.py` sha256: `97d30c485643e443fc9e96ddf046a0912844ca1359b400beb4836df22e1a656b` — matches the committed C6 blob exactly.
- `tests/dose_verification_sandbox/test_span_attribution.py` sha256: `1229849c5c49ec78278cc49cee33ab37967d4cfc01d0d27597d9c3b3a4825b6c` — matches.

## Source DB hashes (re-verified)

| Database | SHA-256 |
|---|---|
| `assembled_regimens.sqlite` | `9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9` |
| `kb_final.db` | `16c31fba2ecafbb9d6bf7c5bc54afee5b46e41d6088cc0ac10492c852abd67dd` |
| `review_workbench_p56.sqlite` | `3e479ee70e59ce9aafa6ba44718dda68d867dbcc660796b81ff63d2b19ca0f29` |

All unchanged since C1. **PASS.**

## Old 365-candidate manifest

`RC030_RANGE_REPROCESS_MANIFEST.json` — sha256 `6797810d4e5ccbe0ff457227b2878cad8d85a58181196cb9be1b5996da2fe239` (untracked, unchanged since C3). Contains exactly 365 rows: 186 `range_attribution_trust == "TRUSTWORTHY"`, 179 `== "SUSPECT_MULTI_DRUG_QUOTE"` (re-verified by direct count this turn).

## Exact 186/179 ID sets

Extracted from the manifest by `range_attribution_trust`; not reproduced as a bare ID list here per the same clinical-data-minimization discipline as C6 (counts and processing pipeline are governed content; the full ID-to-quote mapping stays in the excluded manifest).

## Safety state (directly measured)

- Assembled rows: 2675
- Calculation eligible: 0
- Approved objects: 0
- `TYPES_MEETING_PRECISION_THRESHOLD`: `set()`
- `review_decisions`: 0
- `review_tasks`: 9153, all `PENDING`
- Clinical Engine: disconnected

## Environmental constraint (unchanged from C6)

No local PDF corpus exists in this environment (`C:\clinrec_downloader` resolves to the repo root). Part VI's PDF-backed `SAFE_TABLE_LINK` classification remains unavailable this turn; table-flagged records are classified `AMBIGUOUS_TABLE_CONTEXT`, exactly as in C6.

## Result

All Phase 0 preconditions hold. Proceeding to reconcile the exact 365-record set and replay all of it (previously-TRUSTWORTHY and previously-SUSPECT alike) through the unchanged committed engine.
