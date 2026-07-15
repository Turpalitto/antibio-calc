# KB Identity Specification

Version: 2.0  
Status: canonical for new Knowledge Base builds

## Contract

Every object has three independent identifiers:

1. `logical_key` — stable identity of one governed clinical fact slot.
2. `content_hash` — exact SHA-256 of canonical semantic content.
3. `id` — immutable version ID derived from type + logical_key + content_hash.

`version` is monotonic only inside one `(type, logical_key)` lineage.

## Canonical content

- UTF-8, Unicode NFKC.
- Dictionaries sorted recursively.
- Strings whitespace-normalized.
- Volatile/non-semantic fields excluded: provenance, source, confidence, normalization status, review state, timestamps and producer-supplied logical key.
- JSON serialized with sorted keys and fixed separators.
- No substring matching.

## Clinical scope

Scope is canonical JSON containing available source-owned fields:

- guideline_id
- PDF basename
- page
- paragraph
- bounding box
- table row/column
- object type

Producer may emit an explicit stable `logical_key`. Consumer hashes and stores it; consumer never infers changed-content lineage across different fallback keys.

Fallback identity is conservative: type + clinical scope + canonical semantic content. Exact rebuild is idempotent; changed fallback content becomes a separate lineage instead of unsafe automatic merge.

## Version rules

- Same logical key + same content hash: idempotent; merge only distinct provenance.
- Same logical key + different content hash: exactly next version; previous active version superseded.
- Different logical keys: unrelated objects, even if JSON contains common substrings.
- Exactly one active object per `(type, logical_key)`.
- Version numbers never jump.
- Completed historical versions remain immutable.

## Legacy policy

Any non-empty DB containing NULL logical keys is `LEGACY_FUZZY_IDENTITY` and write-blocked. It remains read-only evidence. Migration/rebuild occurs into a new artifact; no in-place mutation.
