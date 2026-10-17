# RC-030 C6.1 — Root-Cause Clusters (365-record strict replay)

Full per-record detail in the excluded `generated/rc030_c61/range_revalidation_365.json`. Aggregate counts below are real, computed from the actual 365-record replay (Pass A, frozen hash recorded in `RC030_C61_BASELINE.md`/final report).

## Cluster: range belongs to another drug / multi-drug alternative

**Count: 223 (`WRONG_RANGE_ANCHOR`, includes both true wrong-drug-anchor and generic no-valid-segment rejections) + 48 (`AMBIGUOUS_ALTERNATIVE_BOUNDARY`) + 3 (`AMBIGUOUS_MULTIPLE_DRUGS`)**

Representative sanitized example (from C6's architecture audit, still representative — regimen 5622): a scalar-dosed drug (e.g. "Ванкомицин 15 мг/кг") appears before "Или" (Or), followed by a second drug with its own genuine range (e.g. "Клиндамицин 0,6-0,9 г"). The engine correctly refuses to link the second drug's range to the first drug.

**Deterministic rule applied:** `hard_boundary_between()` detects the `или` separator between the antibiotic span and the range span; `same_segment` becomes `False`; the candidate is excluded from `valid`.

**Future remediation:** none needed for these — this is exactly the intended fail-closed behavior. Where a genuinely single-drug quote wrongly detects an "extra" antibiotic mention (e.g. a class-name prefix like "Цефалоспорины I–II поколений" partially matching an unrelated dictionary entry), tightening the antibiotic-span matcher's precision could reduce false multi-drug detection — deferred, dictionary-precision work, not a safety fix.

**PDF requirement:** none. **Dictionary requirement:** possible false-positive reduction (see above). **Owner-review requirement:** yes, every record in this cluster.

## Cluster: dictionary coverage gap

**Count: 40 (`DICTIONARY_GAP`)**

The true dose range is real and structurally would be a strong SAFE candidate, but zero antibiotic mentions in the source text matched the governed `DRUG_SYNONYMS` dictionary (117 entries) — likely a missing synonym/spelling/compound-name variant not yet in `medical_dictionary/drug_synonyms.json`.

**Deterministic rule applied:** `find_antibiotic_spans()` returned an empty list; `attribute()` now returns `DICTIONARY_GAP` (a real fix made this turn — previously mislabeled `AMBIGUOUS_MULTIPLE_DRUGS`, which incorrectly implied competing drugs were seen).

**Future remediation:** expand `medical_dictionary/drug_synonyms.json` coverage for the specific missing forms (would need per-record source inspection to identify each missing alias — out of C6.1 scope, which is engine/tooling, not dictionary curation). **Dictionary requirement: yes, primary blocker for this cluster.** **Owner-review requirement:** yes.

## Cluster: table-flattened source text

**Count: 23 (`AMBIGUOUS_TABLE_CONTEXT`)**

Source quotes with dense multi-line numeric layout (heuristically detected: >3 newlines, >20 digit characters), consistent with a flattened table extraction. No PDF-layout recovery is available in this environment (see baseline), so these are honestly deferred rather than guessed at.

**PDF requirement: yes, primary blocker.** **Owner-review requirement:** yes.

## Cluster: not a true dose range

**Count: 26 (`NOT_A_DOSE_RANGE`)**

No numeric span survived the unit-whitelist + exclusion-rule filtering (age/duration/interval/maximum/non-increasing) — either genuinely no range exists in the quote, or the range's unit doesn't match the dose-unit whitelist (e.g. a malformed OCR-spaced unit token not recognized).

**Future remediation:** could expand the unit-token whitelist for known OCR spacing variants — deferred, dictionary-adjacent work. **Owner-review requirement:** yes (to confirm "genuinely no range" vs. "range present but unit-token unrecognized").

## Cluster: loading/maintenance phase conflict

**Count: 2 (`AMBIGUOUS_LOADING_MAINTENANCE`)**

Explicit phase-marker vocabulary (нагрузочная/поддерживающая/затем/далее) detected between a candidate drug and range. Correctly excluded — a range must never attach across a loading/maintenance transition per the mission's Phase 10 requirement.

**Known related limitation:** perioperative timing language ("во время операции"/"после операции", regimen 5584 from C6) is NOT recognized by the current phase-marker regex and instead falls into the generic `WRONG_RANGE_ANCHOR` bucket rather than this one — the safety outcome is identical (never SAFE), only the specific label is less precise. Documented as a deferred refinement, not a defect (per Phase 18: no engine code change without a concrete regression-provable improvement; expanding phase vocabulary without full validation against all 365 records risks scope creep beyond what this turn verified).

## No clusters observed this turn

- **OCR corruption**: not directly detectable from `source_quote` text alone in this environment (no OCR comparison pipeline available — see PDF constraint).
- **Combination-drug ambiguity**: partially covered by the "range belongs to another drug" cluster above; no distinct combination-specific failure pattern was isolated beyond that.
- **Source truncation / malformed extracted text**: 0 records hit `SOURCE_INCOMPLETE`/`SOURCE_CORRUPTED` — every one of the 365 `source_quote` values was non-empty and syntactically processable.

## Summary table

| Cluster | Count | PDF needed | Dictionary needed | Regimen-split needed | Owner review needed |
|---|---|---|---|---|---|
| Wrong-drug/alternative boundary | 274 (223+48+3) | No | Maybe (precision) | No | Yes |
| Dictionary gap | 40 | No | **Yes** | No | Yes |
| Table-flattened | 23 | **Yes** | No | No | Yes |
| Not a dose range | 26 | No | Maybe (unit tokens) | No | Yes |
| Loading/maintenance | 2 | No | No | Maybe | Yes |
| **Total** | **365** | | | | |
