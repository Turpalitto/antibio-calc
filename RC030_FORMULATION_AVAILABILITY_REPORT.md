# RC-030 Formulation Data Availability Audit

## Schema check

`assembled_regimens` has 31 columns (`regimen_id` … `created_at`); none of them represent concentration, strength, dosage form, or product identifier. There is no `concentration_mg_per_ml`, `strength`, `dosage_form`, or `product_id` column anywhere in the schema.

## Governed dictionary check

`medical_dictionary/unit_dictionary.json` (33 entries, dose-unit synonym → canonical abbreviation) contains only `g`, `mg`, `mcg`, `ml`, `mg/kg`, `mg/kg/day`, `IU`, `thousand_IU` — no concentration unit (`mg/mL`, `mg per 5 mL`, tablet-strength) exists anywhere in this dictionary. No other file under `medical_dictionary/` (`drug_atc.json`, `drug_groups.json`, `drug_synonyms.json`, `duration_dictionary.json`, `frequency_dictionary.json`, `pregnancy_dictionary.json`, `renal_dictionary.json`, `route_dictionary.json`) carries formulation/product data.

## Source-text search

Scanned all 2,675 `source_quote` values for concentration-looking phrases (`мг/мл`, `мг в N мл`, `mg/ml`, `таблетк`, `капсул`, `суспенз`): **40 of 2,675 rows (1.5%)** contain a match — almost always a dosage-form word (e.g. "в таблетках", "в суспензии") describing the recommended route/form, not a machine-usable numeric concentration.

## Classification

| Category | Count / basis |
|---|---|
| SOURCE_BACKED (explicit numeric concentration, e.g. "125 mg/5 mL") | 0 confirmed — no row was found with both a numeric concentration value and a clear regimen linkage in this pass |
| DICTIONARY_BACKED | 0 — no formulation dictionary exists in the repository |
| PRODUCT_SPECIFIC | 0 — no product identifiers exist in the schema |
| AMBIGUOUS | 40 — dosage-form words present in `source_quote` but no extractable numeric concentration |
| **ABSENT** | **2,635** (98.5%) — no formulation signal of any kind |

## Conclusion

Formulation/concentration data does not exist as governed, machine-usable repository data. `convert_to_volume()` in `dose_verification_sandbox/calculator.py` already requires an explicit, caller-supplied `concentration_mg_per_ml` and never infers one — this audit confirms that requirement cannot currently be satisfied from any repository source for any regimen. **Formulation conversion remains disabled for the entire corpus**, consistent with the existing fail-closed design; no change is proposed.
