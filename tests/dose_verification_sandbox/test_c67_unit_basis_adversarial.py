"""RC-030 C6.7 Part VIII/XIII — adversarial regression tests for the
absolute-vs-per-kilogram unit-basis conflation found during the C6.7 audit
(see RC030_C67_UNIT_NORMALIZATION_AUDIT.md). These are characterization
tests: they document the *current* behavior of `_base_unit()` (which does
not yet distinguish `mg` from `mg/kg` from `mg/kg/day`) so that a future
fix is provable against a concrete before/after, per the owner's
requirement that any deterministic-rule change be proven by a regression
test and a full replay, not merely asserted safe.
"""
from __future__ import annotations

from dose_verification_sandbox.span_attribution import _base_unit, attribute, normalize_text


def test_base_unit_currently_conflates_absolute_and_per_kilogram():
    """Characterization test: mg (absolute) and mg/kg (per-weight) are NOT
    clinically interchangeable, but _base_unit() currently treats them as
    the same base unit because it only compares the token before the first
    '/'. This test exists to make the current, real behavior explicit and
    fail loudly if it silently changes without a corresponding fix commit
    updating RC030_C67_UNIT_NORMALIZATION_AUDIT.md."""
    assert _base_unit("mg") == _base_unit("mg/kg") == "mg"
    assert _base_unit("мг") == _base_unit("мг/кг/сут") == "mg"


def test_base_unit_correctly_rejects_genuinely_different_units():
    """Sanity boundary: the conflation above is specific to the '/'-shape
    stripping, not a general loosening -- truly different substances/units
    must still not match."""
    assert _base_unit("mmol") != _base_unit("mg")
    assert _base_unit("g") != _base_unit("mcg")
    assert _base_unit("") != _base_unit("мг")


def test_spelled_out_per_kg_per_day_qualifier_is_truncated_by_the_range_regex():
    """Real defect found in the 117-candidate manifest (regimen_id 5917/
    5918/5441/5442/5475/5478): when source text spells out the per-weight
    qualifier in words ('мг на кг массы тела в сутки') rather than the
    compact token ('мг/кг/сут'), find_range_spans' regex only captures the
    bare 'мг' before the words start, silently losing the qualifier. The
    numeric bounds are still recovered correctly -- only unit_raw is
    misleading. Documented here as a characterization test, not a fix."""
    from dose_verification_sandbox.span_attribution import find_range_spans

    text = ("детям первых трех месяцев жизни - 20-40 мг на кг массы тела в сутки "
            "(при тяжелых инфекциях доза может быть удвоена)")
    norm = normalize_text(text)
    spans = find_range_spans(norm.normalized)
    true_spans = [s for s in spans if s.excluded_reason is None]
    assert len(true_spans) == 1
    # the real dose basis is mg/kg/day, but the regex only captured "мг"
    assert true_spans[0].unit_raw == "мг"
    assert true_spans[0].lower == 20.0
    assert true_spans[0].upper == 40.0


def test_absolute_dose_incorrectly_unit_matches_a_per_kg_structured_field():
    """End-to-end characterization: attribute() will currently report
    unit_match=True (via SAFE_EXACT_LINK/SAFE_SINGLE_CANDIDATE) for a
    per-kilogram structured_unit against an absolute-mg range span, because
    _base_unit() strips the '/kg' qualifier from both sides before
    comparing. A single antibiotic mention with one true range is used so
    the only variable under test is the unit-match gate."""
    text = "амоксициллин** 20-40 мг на кг массы тела в сутки"
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized,
        known_antibiotic_raw="амоксициллин",
        current_scalar=20.0,
        current_unit="mg/kg",  # per-kilogram structured unit
        table_context=False,
    )
    # current (defective) behavior: this is treated as a valid unit match
    # and produces a SAFE_* classification despite the captured range's
    # unit_raw ("мг") not literally carrying the /kg qualifier.
    assert result.classification in ("SAFE_EXACT_LINK", "SAFE_SINGLE_CANDIDATE")
    assert result.selected_range is not None
    assert result.selected_range.unit_raw == "мг"
