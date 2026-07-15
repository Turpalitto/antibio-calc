"""medical_dictionary — production-grade medical terminology database.

Independent subsystem. JSON dictionaries are the source of truth.
Loaded by medical_normalizer/dictionary.py (drug_synonyms, route, unit, drug_atc, drug_groups).
frequency/duration/pregnancy/renal JSON are reference terminology (not wired into parsers).

Rules:
    - Never auto-accept candidates (see dictionary_candidates.json).
    - Additions only to JSON files.
    - metadata.json version bumped on every change.
"""
