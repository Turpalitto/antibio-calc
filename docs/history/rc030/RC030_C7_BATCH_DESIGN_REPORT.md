# RC-030 / C7 Part IV — Review Batch Design and Control Records

## Batches (Phase 6)

11 deterministic batches from the 113 ready tasks, following the spec's recommended shape:

| Batch | Category | Task count | PDF count | Complexity |
|---|---|---|---|---|
| batch_01_exact | EXACT_LINK_CONFIRMATION | 12 | see manifest | LOW |
| batch_02_exact | EXACT_LINK_CONFIRMATION | 12 | see manifest | LOW |
| batch_03_exact | EXACT_LINK_CONFIRMATION | 12 | see manifest | LOW |
| batch_04_engine_disagreement | ENGINE_DISAGREEMENT | 11 | see manifest | MEDIUM |
| batch_05_unit_basis | UNIT_BASIS_REVIEW | 12 | see manifest | MEDIUM |
| batch_06_unit_basis | UNIT_BASIS_REVIEW | 12 | see manifest | MEDIUM |
| batch_07_unit_basis | UNIT_BASIS_REVIEW | 12 | see manifest | MEDIUM |
| batch_08_unit_basis | UNIT_BASIS_REVIEW | 7 | see manifest | MEDIUM |
| batch_09_table_review | TABLE_REVIEW | 8 | see manifest | HIGH |
| batch_10_single_candidate | GENERAL_SINGLE_CANDIDATE | 12 | see manifest | LOW |
| batch_11_single_candidate | GENERAL_SINGLE_CANDIDATE | 3 | see manifest | LOW |
| **Total** | | **113** | | |

Exact PDF counts, per-batch task-unit-ID lists: `generated/rc030_c7/batch_manifest.json` / `review_batches/c7/batch_manifest.json`. No related duplicate claims exist to keep together (Part II found 0 duplicates), so the "don't split duplicates across batches" constraint is vacuously satisfied. Complexity is `LOW`/`MEDIUM`/`HIGH` only — no precise time estimate is fabricated, per the owner's explicit instruction.

## Control records (Phase 7)

4 synthetic controls, `generated/rc030_c7/synthetic_controls.json` — one each: `CONFIRMING`, `WRONG_ANCHOR`, `AMBIGUOUS`, `SOURCE_BLOCKED`. All use `regimen_id` values prefixed `TEST-CONTROL-*` (never a genuine task ID — cross-checked against all 113 real `unit_id`/`regimen_id` values, no collision), all `test_event: true`, all reference a PDF filename (`SYNTHETIC_TEST_ONLY.pdf`) that does not exist in the real corpus. **Kept entirely separate from `review_tasks_ready.json` / the batch manifest — never merged into governed precision input.**
