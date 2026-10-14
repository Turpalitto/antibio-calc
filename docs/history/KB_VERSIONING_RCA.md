# KB Versioning Root Cause Analysis

## Defect

Legacy `_get_by_key` executed `content LIKE '%fragment%'` against serialized JSON. Common text such as `противопоказан` matched unrelated facts. Consumer then incremented the matched row version and superseded it.

## Evidence

- Real `kb_p44.db` maximum version: 1986.
- High versions form sequences of generic Contraindication content across different pages/documents.
- Stable object ID was content-derived while version predecessor was substring-derived. These represented incompatible identity vocabularies.

## Root cause

No persisted logical identity column. Deduplication, content equality and lineage were conflated into one fuzzy query.

## Correction

- Persist `logical_key`, `content_hash`, `clinical_scope`.
- Query indexed exact equality only.
- Write-block legacy non-empty DBs.
- Rebuild/migrate into a separate artifact after tests and invariant validation.

No Clinical Engine or medical logic changes.
