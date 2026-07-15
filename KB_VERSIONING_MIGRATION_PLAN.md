# KB Versioning Migration Plan

## Safety

Baseline `kb_p44.db` is immutable. SHA-256: `2FF88154BBEDEFC37F2331BB6C5D25258F5DAAA188BA525D76EA996E076A3BE9`.

## Plan

1. Ship identity module and collision/idempotency/lineage tests.
2. Block writes to legacy DBs with NULL logical keys.
3. Create new empty v2 DB.
4. Rebuild from certified source pipeline using canonical identity.
5. Compare object/provenance counts, source coverage and semantic yield.
6. Run lineage invariants: exact equality, linear versions, unique active, no jumps.
7. Preserve old artifact and hash as rollback target.
8. Cutover only after independent audit and owner approval.

## Why no in-place backfill

Legacy versions were created from invalid fuzzy predecessors. Their intended logical lineage cannot be recovered from row data without medical/source adjudication. Inventing keys would manufacture history. Clean rebuild preserves source truth and leaves old evidence intact.

## Rollback

Stop using new path and restore configuration to immutable baseline artifact. No byte changes required.
