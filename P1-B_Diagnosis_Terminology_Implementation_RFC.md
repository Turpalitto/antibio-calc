# P1-B Diagnosis Terminology Implementation RFC (lightweight)

**Date:** 2026-07-11  
**Status:** RFC ACCEPTED + IMPLEMENTED + ACCEPTED + FROZEN + CLOSED. Fixture isolation complete. All AC satisfied. 
**Type:** Clinical decision quality contract.  
**Principle:** Every change answers "How does this improve clinical decision quality?" Additive only. No redesign. No P0 touch. No P1-A touch.  

**Review feedback incorporated (2026-07-11):**  
- Added confidence (HIGH/MEDIUM/LOW or numeric) + Reason to every traceability output.  
- Added one negative Golden Case requirement (prove incorrect guideline NOT selected).  
- Updated AC, scenarios, traceability section, validation path.  
Both positive routing improvement + negative exclusion must be proven via Golden Cases before P1-B can be marked complete.

**Laws active here (first real application):**  
- Clinical Evidence Rule: real patient scenarios + measurable benefit via Golden Cases.  
- Clinical Traceability Rule: every normalization answers the 7 questions. No black box.  
- Optimization Rule: only changes that improve routing accuracy, reduce incorrect guideline selection, and deliver physician-visible benefit.  

Diagnosis Terminology is the first stage where these three laws must operate on real clinical input. "Почему 'острый гайморит', 'острый синусит ВЧП' и J01.0 — это один и тот же клинический сценарий?" must be explainable.

Focus: clinical decision quality (correct guideline routing for physician recommendations). Not architecture.

## 1. Which diagnosis terminology problems are solved?

Current state (from P1-B_Diagnosis_Terminology_Analysis.md): exact string match (lower) + exact ICD upper only. No synonyms, no normalization, no trace. 895 entries, 101 conflicts, 127 duplicate names. Re-lookup duplication in RegimenLoad. Physician wording variants fail -> NO_MATCH or wrong guideline.

Problems solved (additive, via TerminologyProvider extension for diagnosis + enhanced lookup):

- **diagnosis synonyms**: "гайморит" == "синусит", "ВЧП" == "верхнечелюстная пазуха", "пневмония внебольничная" == "внебольничная пневмония".
- **ICD normalization**: J01.0 / J01.00 / J01 -> canonical "J01"; J18.0 / J18 -> "J18"; prefix/prefix-group handling for variants stored in index.
- **spelling variants / case / punctuation**: "Острый ГАЙМОРИТ", "острый гайморит.", "острый  гайморит" -> normalized form.
- **abbreviations**: ВЧП, CAP-equivalent Russian phrasing, "ОРВИ осложненная" patterns common in notes.
- **physician wording**: free-text "острый синусит верхнечелюстных пазух", "community-acquired pneumonia" mapping (Russian primary), "острый цистит неосложненный".
- **multiple diagnosis names referring to the same guideline**: index has "Внебольничная пневмония у взрослых" + "Пневмония внебольничная" + sub-variants all map to same guideline_id set (e.g. 1770). Normalization collapses to correct guideline(s) without duplication or loss.

Legacy: only direct hits on stored diagnosis_name or icd10_codes. Misses  common variants -> routing failure.

## 2. How does each improvement affect physician-visible recommendations?

Each maps to correct guideline_ids earlier and reliably:

- Synonyms + wording: correct guideline loaded instead of NO_MATCH or fallback to wrong. RegimenLoad succeeds with right year + regimens. Recommendations appear for the actual clinical scenario.
- ICD normalization: J01.0 input now hits J01 guideline. Avoids "Diagnosis/ICD-10 not found" engine_note. Physician sees first-line regimens from КР for that diagnosis.
- Spelling/abbrev: tolerant input from EHR notes or quick typing. No silent failure.
- Multiple names same guideline: one guideline wins consistently. Avoids duplicate/conflicting candidates or split routing.

Clinical consequence: 
- More accurate routing = correct antibiotic classes, dosing, safety rules, therapy lines from the right КР.
- Fewer NO_REGIMENS or NO_MATCH -> physician gets actionable output instead of blank or manual lookup.
- Trace explains "why this guideline" -> trust + audit.
- Incorrect guideline selection decreases: e.g. sinusitis input no longer routes to unrelated or zero regimens (risk of delayed treatment or wrong abx).

No change to P0 contracts or P1-A drug path. Additive behind existing use_terminology_binding or new diagnosis flag if needed. Golden Cases prove delta.

## 3. Real clinical scenarios

### Scenario 1: Acute sinusitis / гайморит variants (common outpatient)
- **physician input**: diagnosis="острый гайморит" (or "острый синусит ВЧП", icd10="J01.0")
- **legacy behavior**: exact lower lookup fails ("острый гайморит" != "Острый бактериальный синусит у взрослых"). ICD J01.0 != "J01". -> guideline_ids=() , StageTrace NO_MATCH, engine_note "Diagnosis/ICD-10 not found". No regimens. Output: empty or generic note.
- **new behavior**: synonym resolve "гайморит"->"синусит", "ВЧП"->full, ICD norm J01.0->"J01" -> hits entries for guideline_ids e.g. "1220"/"1632".
- **guideline selected**: "Острый синусит" (guideline_id 1220/1632, title "Острый синусит", ICD J01, year 2021/2024).
- **traceability output** (per Clinical Traceability Rule):
  Diagnosis Resolution
    Original: "острый гайморит"
    Normalized: "Острый бактериальный синусит у взрослых"
    ICD: "J01"
    Synonym: "гайморит → синусит"
    Confidence: HIGH (0.98)
    Reason: ICD exact + synonym normalization + normalized name exact match in index
    Source: diagnosis_synonym_map + ICD_prefix_norm
  - why the selected guideline won: ICD match + normalized name match to entry with guideline 1220; highest evidence year or explicit rule.
  - why alternatives lost: other guidelines have no matching ICD/name after norm; conflicts resolved by curation or explicit (no auto).
  - full chain: DiagnosisMatch -> terminology.resolve_diagnosis -> lookup -> guideline_ids.
- **measurable clinical benefit**: routing success 0/1 -> 1/1 correct guideline. Physician receives evidence-based first-line regimens (e.g. amoxicillin or per КР) instead of no output. Reduces diagnostic delay, avoids empirical wrong choice. Golden Case will assert guideline_ids contains "1220", no NO_MATCH note, accepted regimens >0.

### Scenario 2: Community-acquired pneumonia (CAP) variants
- **physician input**: diagnosis="внебольничная пневмония" (or "пневмония внебольничная", icd10="J18")
- **legacy behavior**: partial exact match possible on some entries ("Пневмония внебольничная") but fails for "внебольничная пневмония" phrasing or full title variants. J18 may hit subset. Risk of incomplete guideline_ids or routing to narrow sub-entry (e.g. risk-factor specific). Re-lookup in RegimenLoad may differ.
- **new behavior**: synonym/alias collapse + ICD norm -> consistent hit on main guideline 1770 ("Внебольничная пневмония у взрослых", ICDs incl J18).
- **guideline selected**: "Внебольничная пневмония у взрослых" (guideline_id 1770, multiple ICD incl. J18).
- **traceability output**:
  Diagnosis Resolution
    Original: "внебольничная пневмония"
    Normalized: "Внебольничная пневмония у взрослых"
    ICD: "J18"
    Synonym: "пневмония внебольничная" alias
    Confidence: HIGH (0.95)
    Reason: ICD group match + synonym alias + primary guideline entry
    Source: diagnosis_alias_map + ICD_group
  - why won: direct match post-norm to primary entry for 1770; guideline_year latest
  - why alt lost: sub-entries (risk factors) deprioritized or merged by curation rule; other pneumonia guidelines no ICD overlap after norm.
- **measurable clinical benefit**: correct guideline always selected regardless of phrasing. Enables proper population_filter, safety, first-line (amox etc per КР). Quantified: on Golden Case set, match rate ↑ for CAP queries. Prevents missed or wrong-regimen output. Golden Case (extension of cap_penicillin_allergy) asserts first guideline 1770, accepted drugs match КР.

### Scenario 3: Acute uncomplicated cystitis wording variants
- **physician input**: diagnosis="острый неосложненный цистит" (or "неосложненный цистит", "острый цистит", icd10="N30.0")
- **legacy behavior**: hits "острый неосложненный цистит" (1127) if exact. "неосложненный цистит" or slight wording misses or hits secondary entries (conflicts noted in meta: 1127/1643). -> inconsistent guideline_ids, possible wrong or duplicate.
- **new behavior**: normalize wording/synonym + ICD -> stable to primary "Цистит у женщин" guideline 1127.
- **guideline selected**: 1127 ("Цистит у женщин", "острый неосложненный цистит").
- **traceability output**:
  Diagnosis Resolution
    Original: "острый неосложненный цистит"
    Normalized: "острый неосложненный цистит"
    ICD: "N30.0"
    Synonym: "неосложненный цистит" → canonical
    Confidence: MEDIUM (0.82)
    Reason: exact name + ICD + curation preference for primary over conflict entry
    Source: index_curation_ledger + direct_name
  - why won: name+ICD match to 1127 entry; curation decision for conflict
  - why alt lost: 1643 is secondary/resistance context, loses on norm + preference for primary.
- **measurable clinical benefit**: consistent routing to correct КР for uncomplicated cystitis (nitrofurantoin etc). Reduces risk of selecting resistance-specific regimen for simple case. Golden Case: assert specific guideline_id, correct first drug, no conflict in trace.

### Negative validation case (prove wrong guideline is NOT selected)

Must demonstrate exclusion of incorrect КР, not only correct selection.

- **physician input**: diagnosis="гайморит" (acute intent, no chronic marker)
- **must NOT route to**: chronic sinusitis guideline (e.g. any entry with "хронический синусит" or equivalent chronic title in index).
- **legacy behavior**: may miss entirely or (if loose) risk wrong bucket due to "синусит" substring.
- **new behavior**: normalization keeps acute context (or lack of "хронический"); synonym to acute sinusitis only; confidence still HIGH for acute, explicitly excludes chronic variants.
- **traceability output** (negative path):
  Diagnosis Resolution
    Original: "гайморит"
    Normalized: "Острый бактериальный синусит у взрослых"
    ICD: "J01"
    Synonym: "гайморит → синусит"
    Confidence: HIGH (0.97)
    Reason: no chronic marker in input; synonym + ICD resolve only to acute entries
    Source: diagnosis_synonym_map + chronic_exclusion_rule
  - why chronic guideline lost: input after norm lacks "хронический" / "recurrent" / "рецидивирующий"; chronic entries require explicit chronic term or different ICD context.
- **Golden Case requirement (negative)**: 
  - query diagnosis="гайморит" (or "острый гайморит")
  - assert: chronic sinusitis guideline_ids NOT present in result.guideline_ids
  - assert: no engine_note that would allow chronic routing
  - (or use expect.not_guideline_ids or equivalent extension)

Similar negative for "тонзиллит" must NOT resolve to "фарингит" guideline (different КР).

Negative cases are mandatory for acceptance. Positive cases alone insufficient.

All scenarios use real index entries. Benefit measured by Golden Cases (new ones + extension of cap_penicillin_allergy) + before/after match counts on test set. Incorrect guideline selection decreases. Physician sees right regimens + full why. Positive + negative routing correctness both required.

## 4. Clinical Acceptance Criteria

The implementation is acceptable only if:

- routing becomes more accurate (exact+norm > exact-only on real variants)
- incorrect guideline selection decreases (fewer wrong/zero guideline_ids on synonym/ICD/ wording inputs)
- traceability explains every normalization decision (original input, normalized, synonym, ICD, why won, why lost, confidence + reason, source)
- Golden Cases prove measurable benefit (positive cases for the 3 scenarios + at least one negative case; both routing success ↑ and incorrect guideline exclusion proven; before/after delta; runner reports success)
- no regressions (all 1159+ tests pass on flag=false or legacy path; same outputs on exact-match cases)

No acceptance on "more coverage" alone. Must demonstrate via scenarios + Golden + trace that physician-visible recs improve (correct КР, fewer misses, explainable).

## 5. Keep the implementation additive.

- No redesign.
- No modifications to P0 (Architecture v3, BundleManifest, Provider Ports contracts, invariants, models, SQLite, medical_normalizer, medical_dictionary frozen as-is).
- No modifications to P1-A (TerminologyProvider drug/ATC/allergy paths, existing get_atc/get_allergy_class/get_mapping, BasicTerminologyProvider, cap_penicillin_allergy Golden, tests for P1-A).
- No changes outside approved scope (diagnosis terminology normalization + trace only; extend resolve_diagnosis and lookup behavior).
- Additive: reuse/extend existing TerminologyProvider + DiagnosisProvider. Feature flag or coexist with legacy exact path. Flag off = exact prior behavior.
- Backwards compat + deterministic.
- Production Guard, curation status, index meta untouched.

Changes limited to: diagnosis synonym/ICD norm logic (data-driven), enhanced trace in DiagnosisMatch/RegimenLoad, new Golden Cases for diagnosis, updates to docs only after acceptance.

## 6. Every normalization step must become traceable.

The engine must always explain (no diagnosis routing black box). Structured output required (example format):

```
Diagnosis Resolution
  Original: "острый гайморит"
  Normalized: "Острый бактериальный синусит у взрослых"
  ICD: "J01"
  Synonym: "гайморит → синусит"
  Confidence: HIGH (0.98)
  Reason: ICD exact + synonym normalization + normalized name exact match in index
  Source: diagnosis_synonym_map v1 + ICD_prefix_norm
```

Required fields for every resolution (success or NO_MATCH):

- original physician input
- normalized diagnosis
- synonym used (if any)
- ICD mapping used (if any)
- why the selected guideline won
- why alternatives lost
- confidence (HIGH / MEDIUM / LOW or 0.0-1.0 numeric)
- reason (short rule-based explanation for confidence)
- source/version of mapping (e.g. diagnosis_synonym_map vX, ICD norm rule)

Simple confidence rule (no complex ML, additive):
- HIGH: exact ICD match + synonym/alias normalization + normalized diagnosis_name exactly present in index
- MEDIUM: ICD match OR strong synonym leads to match
- LOW: spelling/punctuation/abbrev only, or weak/partial ICD prefix
- 0.0 or NONE: no match after all steps

Trace must be carried in StageTrace (augmented), Recommendation.trace, and exposed in RecommendationSet / DecisionReport / build_report / engine notes.

Current NO_MATCH trace extended to full path even on success. Every rec carries the diagnosis normalization chain.

Clinical Traceability Rule (law) now applies end-to-end for diagnosis -> guideline. This structure will be reusable in P2+.

## Clinical Validation Path

- Add/extend Golden Cases in clinical_engine/golden_cases/ for the 3 positive scenarios (query variants, expect correct guideline_ids + no bad notes + confidence level recorded).
- Add at least one negative Golden Case (e.g. "гайморит" must not select chronic sinusitis guideline; "тонзиллит" must not select фарингит). (Support for not_guideline_id in runner added during audit remediation to make exclusion provable.)
- Run golden runner before/after (delta routing success + incorrect exclusion proven).
- Existing tests unchanged on legacy.
- Trace assertions in tests for all required fields including confidence + reason.
- Physician review of scenarios + benefit.

## Definition of Done (pre-freeze)

- RFC accepted.
- Impl additive only (post review).
- All AC met with evidence.
- Docs updated (incl this RFC, PROJECT_STATE, etc.).
- No regressions.
- Handoff complete.

Post-approval: implement additive only, tests, Golden validation (positive + negative cases), clinical validation, acceptance review, freeze, documentation, consistency audit, cross-IDE handoff.

Do not mark P1-B complete until measurable routing improvement is demonstrated using both positive and negative Golden Cases.

**RFC ready for final ACCEPTED. Proceed to implementation only after explicit ACCEPTED.**

No scope expansion. No redesign. No P0 modifications. No P1-A modifications.
Implement only what is defined in this RFC.

**Stop here until explicit go. Do not implement yet.**

(Reference: P1-B_Diagnosis_Terminology_Analysis.md, P1_Terminology_Implementation_RFC.md (P1-A frozen), DECISIONS.md laws, clinical_engine/resources/diagnosis_index.json entries, diagnosis_reader.py, diagnosis_match.py, models.py.)