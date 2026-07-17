"""RC-030 C6.7/C6.8 — regression tests proving the fix for the absolute-vs-
per-kilogram unit-basis conflation found during the C6.7 audit (see
RC030_C67_UNIT_NORMALIZATION_AUDIT.md) and repaired in C6.8 by replacing
`_base_unit()`'s leading-token comparison with the structured
`DoseUnitSignature`/`compare_dose_units()` model (see
RC030_C68_UNIT_VOCABULARY_AUDIT.md). `_base_unit()` itself was removed as
dead code once its only call site was replaced.
"""
from __future__ import annotations

from dose_verification_sandbox.dose_unit_signature import (
    COMPATIBLE_BASIS_UNSPECIFIED, EXACT_EQUIVALENT, compare_dose_units, parse_dose_unit,
)
from dose_verification_sandbox.span_attribution import (
    SAFE_EXACT_LINK, SAFE_SINGLE_CANDIDATE, attribute, find_range_spans, normalize_text,
)


def test_absolute_and_per_kilogram_are_no_longer_conflated():
    """mg (absolute) and mg/kg (per-weight) are NOT clinically
    interchangeable. Unlike the old _base_unit(), compare_dose_units()
    reports this explicitly rather than silently treating them as equal."""
    assert compare_dose_units(parse_dose_unit("mg"), parse_dose_unit("mg/kg")) != EXACT_EQUIVALENT
    assert compare_dose_units(parse_dose_unit("мг"), parse_dose_unit("мг/кг/сут")) != EXACT_EQUIVALENT


def test_genuinely_different_units_still_correctly_rejected():
    """Sanity boundary carried over from the C6.7 characterization: truly
    different substances/units must still not match."""
    assert compare_dose_units(parse_dose_unit("mmol"), parse_dose_unit("mg")) not in (EXACT_EQUIVALENT, COMPATIBLE_BASIS_UNSPECIFIED)
    assert compare_dose_units(parse_dose_unit("g"), parse_dose_unit("mcg")) not in (EXACT_EQUIVALENT, COMPATIBLE_BASIS_UNSPECIFIED)


def test_spelled_out_per_kg_per_day_qualifier_is_now_captured_in_full():
    """Fixed in C6.8: regimen_id 5917/5918/5441/5442/5475/5478's source text
    spells the per-weight-per-day qualifier in words ('мг на кг массы тела
    в сутки') rather than the compact token ('мг/кг/сут'). The range regex
    now recognizes this spelled-out construction explicitly, so unit_raw
    carries the full qualifier instead of being silently truncated to the
    bare substance unit 'мг'."""
    text = ("детям первых трех месяцев жизни - 20-40 мг на кг массы тела в сутки "
            "(при тяжелых инфекциях доза может быть удвоена)")
    norm = normalize_text(text)
    spans = find_range_spans(norm.normalized)
    true_spans = [s for s in spans if s.excluded_reason is None]
    assert len(true_spans) == 1
    assert true_spans[0].unit_raw == "мг на кг массы тела в сутки"
    assert true_spans[0].lower == 20.0
    assert true_spans[0].upper == 40.0

    sig = parse_dose_unit(true_spans[0].unit_raw)
    assert sig.numerator_unit == "mg"
    assert sig.weight_denominator == "kg"
    assert sig.time_denominator == "day"


def test_absolute_dose_no_longer_falsely_exact_matches_a_per_kg_structured_field():
    """End-to-end fix proof: a per-kilogram structured_unit ('mg/kg') against
    the now-fully-captured per-kilogram-per-day source range ('мг на кг
    массы тела в сутки') is COMPATIBLE_BASIS_UNSPECIFIED, not
    EXACT_EQUIVALENT (the source is more specific -- explicit /day -- than
    the structured field) -- so this can be at most SAFE_SINGLE_CANDIDATE,
    never SAFE_EXACT_LINK, closing the real defect found in C6.7 for these
    6 previously-mis-classified exact-link records."""
    text = "амоксициллин** 20-40 мг на кг массы тела в сутки"
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized,
        known_antibiotic_raw="амоксициллин",
        current_scalar=20.0,
        current_unit="mg/kg",
        table_context=False,
    )
    assert result.classification == SAFE_SINGLE_CANDIDATE
    assert result.classification != SAFE_EXACT_LINK
    assert result.selected_range is not None
    assert result.selected_range.unit_raw == "мг на кг массы тела в сутки"
    assert result.score_components["unit_compatibility"] == COMPATIBLE_BASIS_UNSPECIFIED


def test_exact_matching_basis_still_reaches_safe_exact_link():
    """Positive control: when the source text's captured unit and the
    structured field genuinely agree on full basis (numerator, weight,
    time), SAFE_EXACT_LINK is still reachable -- the fix downgrades
    basis-ambiguous cases, it does not make exact-link unreachable."""
    text = "амоксициллин** 20-40 мг/кг/сут в 3 приема"
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized,
        known_antibiotic_raw="амоксициллин",
        current_scalar=20.0,
        current_unit="mg/kg/day",
        table_context=False,
    )
    assert result.classification == SAFE_EXACT_LINK
    assert result.score_components["unit_compatibility"] == EXACT_EQUIVALENT
