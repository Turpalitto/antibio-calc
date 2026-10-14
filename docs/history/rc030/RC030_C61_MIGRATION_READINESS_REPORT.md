# RC-030 C6.1 — Migration Readiness Report

**AUTHORITATIVE MIGRATION NOT AUTHORIZED. NOT EXECUTED. NO AUTHORITATIVE SQLITE MODIFIED IN THIS TURN.**

## The old TRUSTWORTHY label is retired

C3/prior-turn's 186-record `TRUSTWORTHY` classification was based solely on "recovered lower bound matches the current structured scalar dose." This turn's strict, independent, span-linked re-derivation of all 186 of those records shows **0 retain a SAFE classification** — the scalar-match signal alone was insufficient proof of correct drug/span attribution, exactly as this turn's owner authorization anticipated. **The `TRUSTWORTHY` label must no longer be used as a migration-readiness signal anywhere in this repository's documentation or tooling going forward.** Only the classifications produced by `dose_verification_sandbox/span_attribution.py` are relevant to migration decisions from this point on.

## SAFE_EXACT_LINK count
**0** (of 365)

## SAFE_TABLE_LINK count
**0** — blocked entirely by the unavailability of a local PDF corpus in this environment (see `RC030_C61_BASELINE.md`).

## SAFE_SINGLE_CANDIDATE count
**0**

## Table/PDF blockers
23 records (`AMBIGUOUS_TABLE_CONTEXT`) are blocked specifically on PDF-layout recovery (DocLayout-YOLO/Table Transformer/PyMuPDF page clipping), which cannot run in this environment. This is the single most PDF-dependent cluster.

## Dictionary blockers
40 records (`DICTIONARY_GAP`) have a true dose range but zero antibiotic dictionary match — the most directly actionable blocker (expand `medical_dictionary/drug_synonyms.json` coverage), though doing so is dictionary-curation work, not engine work, and requires per-record source inspection outside this turn's scope.

## Source blockers
0 (`SOURCE_INCOMPLETE`/`SOURCE_CORRUPTED`) — every one of the 365 `source_quote` values is present and processable.

## Owner-review requirements
All 365 records require owner review before any could be considered for a future migration — none reach a classification that would exempt them. The compact `RC030_C61_OWNER_REVIEW_QUEUE.json` (85 items) prioritizes the most actionable subset (dictionary gaps, table-blocked, loading/maintenance, plus a representative sample of revoked former-trust records).

## Expected authoritative changed rows if a future migration is approved
**0**, given the current result set. A future migration proposal would need either (a) real PDF-corpus access to resolve the 23 table-blocked records, (b) dictionary expansion to resolve some of the 40 dictionary-gap records into a scorable state, or (c) owner-provided manual linkage for individual high-value cases — none of which happened this turn.

## Rollback requirements (unchanged from C3/C6 proposals)
Snapshot authoritative DBs (sha256 recorded) before any future migration; additive columns (`dose_min, dose_max, dose_is_range, dose_range_raw, dose_source_start, dose_source_end, dose_range_confidence, range_provenance`) allow `DROP COLUMN`/table-rebuild or snapshot restore.

## Exact changed-field allowlist (unchanged)
The 8 additive columns only. `dose` (scalar) and every clinical field stay byte-identical in any future migration.

## Current status

**AUTHORITATIVE MIGRATION NOT AUTHORIZED.** Given 0 qualifying rows across the entire 365-candidate corpus (not just the 179 previously-SUSPECT subset — the previously-TRUSTWORTHY 186 fare no better under strict re-validation), there is currently nothing eligible to migrate. This is a stronger, more conservative finding than C6's report on the 179-subset alone, and should be treated as the current authoritative status of the whole range-recovery effort until PDF access and/or dictionary coverage improve.
