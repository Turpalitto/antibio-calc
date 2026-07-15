"""Regression test for RC-029.

Root cause (fixed 2026-07-15): BasicTerminologyProvider.__init__ mutated the
functools.lru_cache-cached dict returned by medical_dictionary.loader.load_drug_atc()
in place, permanently corrupting the process-wide cache the first time any code
constructed the provider. This broke medical_normalizer/tests/test_medical_dictionary_loader.py
::TestLoaderDrugAtc::test_empty_until_review whenever a test constructing
BasicTerminologyProvider ran first in the same process (see
MEDICAL_DICTIONARY_TEST_ISOLATION_RCA.md for the full investigation).
"""

from __future__ import annotations

from clinical_engine.pipeline import ClinicalConstants
from clinical_engine.terminology import BasicTerminologyProvider
from medical_dictionary.loader import load_drug_atc


def test_constructing_provider_does_not_mutate_cached_drug_atc() -> None:
    before = load_drug_atc()
    assert before == {}, "drug_atc.json is expected empty until manual review"

    constants = ClinicalConstants(
        age_bands={}, renal_thresholds={}, allergy_class_map={}, allergy_class_hierarchy={},
    )
    provider = BasicTerminologyProvider(constants)

    # Provider gets its own demo entry...
    assert provider.get_atc("unmapped_pen") == "J01CA04"

    # ...but the shared, lru_cache'd loader result must remain untouched.
    after = load_drug_atc()
    assert after == {}, "load_drug_atc() cache was mutated by BasicTerminologyProvider construction"
    assert after is not provider._atc_map, "provider must hold its own copy, not the cached singleton"


def test_multiple_providers_do_not_accumulate_state_in_shared_cache() -> None:
    constants = ClinicalConstants(
        age_bands={}, renal_thresholds={}, allergy_class_map={}, allergy_class_hierarchy={},
    )
    BasicTerminologyProvider(constants)
    BasicTerminologyProvider(constants)
    BasicTerminologyProvider(constants)
    assert load_drug_atc() == {}
