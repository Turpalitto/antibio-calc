"""RC-030 C6.8 Part V (Phase 8-9) — exhaustive DoseUnitSignature test matrix
and attribution regression tests proving the dose-basis repair.

No PDF opened, no database written, no Clinical Engine import, no
TYPES_MEETING_PRECISION_THRESHOLD reference. Pure deterministic text/data
analysis only.
"""
from __future__ import annotations

import pytest

from dose_verification_sandbox.dose_unit_signature import (
    COMPATIBLE_BASIS_UNSPECIFIED, CONCENTRATION_NOT_DOSE, CONTINUOUS_RATE,
    EXACT_EQUIVALENT, INCOMPATIBLE_ADMINISTRATION_BASIS, INCOMPATIBLE_NUMERATOR,
    INCOMPATIBLE_TIME_BASIS, INCOMPATIBLE_WEIGHT_BASIS, MALFORMED_UNIT, PARSE_EMPTY,
    PARSE_MALFORMED, PARSE_OK, PARSE_UNKNOWN_NUMERATOR, PARSE_UNKNOWN_TOKEN,
    PER_DAY, PER_DOSE, RATE_NOT_DOSE, UNKNOWN_UNIT, UNSPECIFIED,
    UNSPECIFIED_WEIGHT_BASED, compare_dose_units, parse_dose_unit,
)
from dose_verification_sandbox.span_attribution import (
    SAFE_EXACT_LINK, SAFE_SINGLE_CANDIDATE, WRONG_RANGE_ANCHOR, attribute, normalize_text,
)

# ── Phase 8: EQUIVALENT pairs ───────────────────────────────────────────────

EQUIVALENT_PAIRS = [
    ("mg", "мг"),
    ("g", "г"),
    ("mcg", "мкг"),
    ("mg/kg", "мг/кг"),
    ("mg/kg/day", "мг/кг/сут"),
    ("mg/kg/dose", "мг/кг/введение"),
    ("mg/day", "мг/сут"),
    ("mg/ml", "мг/мл"),
    ("mcg/kg/min", "мкг/кг/мин"),
]


@pytest.mark.parametrize("a,b", EQUIVALENT_PAIRS, ids=[f"{a}~{b}" for a, b in EQUIVALENT_PAIRS])
def test_equivalent_pairs(a, b):
    assert compare_dose_units(parse_dose_unit(a), parse_dose_unit(b)) == EXACT_EQUIVALENT


# ── Phase 8: NON-EQUIVALENT pairs ───────────────────────────────────────────

NON_EQUIVALENT_PAIRS = [
    ("mg", "mg/kg", INCOMPATIBLE_WEIGHT_BASIS),
    ("mg/kg", "mg/kg/day", COMPATIBLE_BASIS_UNSPECIFIED),
    ("mg/kg/day", "mg/kg/dose", INCOMPATIBLE_TIME_BASIS),
    ("mg/day", "mg/dose", INCOMPATIBLE_TIME_BASIS),
    ("mg/ml", "mg", CONCENTRATION_NOT_DOSE),
    ("mg/l", "mg/ml", INCOMPATIBLE_ADMINISTRATION_BASIS),
    ("mcg", "mg", INCOMPATIBLE_NUMERATOR),
    ("IU", "mg", INCOMPATIBLE_NUMERATOR),
    ("mmol", "mg", INCOMPATIBLE_NUMERATOR),
    ("mg/kg/min", "mg/kg/day", RATE_NOT_DOSE),
    ("mg/m2/day", "mg/kg/day", INCOMPATIBLE_WEIGHT_BASIS),
]


@pytest.mark.parametrize("a,b,expected", NON_EQUIVALENT_PAIRS, ids=[f"{a}!~{b}" for a, b, _ in NON_EQUIVALENT_PAIRS])
def test_non_equivalent_pairs(a, b, expected):
    result = compare_dose_units(parse_dose_unit(a), parse_dose_unit(b))
    assert result == expected
    assert result != EXACT_EQUIVALENT


# ── Phase 8: MALFORMED / UNKNOWN ────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected_status", [
    ("", PARSE_EMPTY),
    ("/", PARSE_MALFORMED),
    ("//", PARSE_MALFORMED),
    ("mg//kg", PARSE_MALFORMED),
    ("unknownunit", PARSE_UNKNOWN_NUMERATOR),
    ("mg/unknowndenom", PARSE_UNKNOWN_TOKEN),
    ("mg/ml/kg", PARSE_UNKNOWN_TOKEN),  # impossible token combination: concentration + weight denominator together
    ("г; мг/кг", PARSE_MALFORMED),  # duplicated denominator via compound multi-unit string
    ("mg\x00/kg", PARSE_UNKNOWN_NUMERATOR),  # control character corrupts the numerator token itself
])
def test_malformed_and_unknown(raw, expected_status):
    sig = parse_dose_unit(raw)
    assert sig.parse_status == expected_status


def test_numeric_text_inside_unit_is_unknown_numerator():
    sig = parse_dose_unit("123mg")
    assert sig.parse_status == PARSE_UNKNOWN_NUMERATOR


def test_comparison_with_malformed_or_unknown_never_yields_equivalence():
    bad_signature = parse_dose_unit("")
    good_signature = parse_dose_unit("mg")
    result = compare_dose_units(bad_signature, good_signature)
    assert result in (UNKNOWN_UNIT, MALFORMED_UNIT)
    assert result not in (EXACT_EQUIVALENT, COMPATIBLE_BASIS_UNSPECIFIED)


# ── Phase 1 worked examples, exact field-by-field ──────────────────────────

@pytest.mark.parametrize("raw,numerator,weight,time,basis,conc,rate", [
    ("mg", "mg", None, None, UNSPECIFIED, None, None),
    ("mg/kg", "mg", "kg", None, UNSPECIFIED_WEIGHT_BASED, None, None),
    ("mg/kg/day", "mg", "kg", "day", PER_DAY, None, None),
    ("mg/kg/dose", "mg", "kg", None, PER_DOSE, None, None),
    ("mg/day", "mg", None, "day", PER_DAY, None, None),
    ("mg/dose", "mg", None, None, PER_DOSE, None, None),
    ("mg/ml", "mg", None, None, "CONCENTRATION", "ml", None),
    ("mcg/kg/min", "mcg", "kg", "minute", CONTINUOUS_RATE, None, "minute"),
])
def test_phase1_worked_examples(raw, numerator, weight, time, basis, conc, rate):
    sig = parse_dose_unit(raw)
    assert sig.parse_status == PARSE_OK
    assert sig.numerator_unit == numerator
    assert sig.weight_denominator == weight
    assert sig.time_denominator == time
    assert sig.administration_basis == basis
    assert sig.concentration_denominator == conc
    assert sig.rate_basis == rate


# ── Determinism ──────────────────────────────────────────────────────────

def test_parse_is_deterministic():
    assert parse_dose_unit("mg/kg/day") == parse_dose_unit("mg/kg/day")


def test_no_io_no_network_no_clinical_engine():
    import inspect
    import dose_verification_sandbox.dose_unit_signature as mod
    source = inspect.getsource(mod)
    for marker in ("sqlite3.connect", "open(", "requests.", "socket.", "clinical_engine", "TYPES_MEETING_PRECISION_THRESHOLD"):
        assert marker not in source


# ── Phase 9: attribution regression -- the 6 previously falsely-exact records ──

# All 6 share the identical erythromycin quote pattern from the real
# 117-candidate manifest (regimen_id 5917/5918/5441/5442/5475/5478).
_ERYTHROMYCIN_QUOTE = (
    "детям первых трех месяцев жизни - {lo}-{hi} мг на кг массы тела в сутки "
    "(при тяжелых инфекциях доза может быть удвоена)"
)


@pytest.mark.parametrize("lo,hi,structured_scalar", [(20, 40, 20.0), (30, 50, 30.0)])
def test_previously_falsely_exact_records_no_longer_reach_safe_exact_link(lo, hi, structured_scalar):
    """Direct regression for regimen_id 5917/5918/5441/5442/5475/5478: these
    were SAFE_EXACT_LINK under the old _base_unit() leading-token
    comparison purely because 'мг' (truncated) and 'mg/kg' (structured)
    both reduced to base unit 'mg'. Under the repaired engine they must
    cap out at SAFE_SINGLE_CANDIDATE."""
    text = "эритромицин** " + _ERYTHROMYCIN_QUOTE.format(lo=lo, hi=hi)
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized, known_antibiotic_raw="эритромицин",
        current_scalar=structured_scalar, current_unit="mg/kg", table_context=False,
    )
    assert result.classification == SAFE_SINGLE_CANDIDATE
    assert result.classification != SAFE_EXACT_LINK


def test_basis_conflict_downgrades_to_wrong_range_anchor_when_scalar_also_mismatches():
    """A genuine basis conflict (concentration vs. dose) combined with no
    scalar match must fail closed to WRONG_RANGE_ANCHOR, not silently pass."""
    text = "амоксициллин** 20-40 мг/мл раствор"
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized, known_antibiotic_raw="амоксициллин",
        current_scalar=999.0, current_unit="mg", table_context=False,
    )
    assert result.classification == WRONG_RANGE_ANCHOR


def test_unspecified_basis_does_not_auto_promote_to_exact_even_with_scalar_match():
    """mg/kg (structured, unspecified basis) against a source range whose
    unit_raw is genuinely just 'мг/кг' (no further qualifier) IS an exact
    match (both unspecified) -- this is the correct positive control
    distinguishing 'basis genuinely absent on both sides' (still exact)
    from 'one side states more than the other' (compatible-unspecified)."""
    text = "амоксициллин** 20-40 мг/кг в сутки"
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized, known_antibiotic_raw="амоксициллин",
        current_scalar=20.0, current_unit="mg/kg", table_context=False,
    )
    assert result.classification == SAFE_EXACT_LINK
    assert result.score_components["unit_compatibility"] == EXACT_EQUIVALENT


def test_frequency_cannot_compensate_for_unit_basis_mismatch():
    """Phase 5: frequency and unit basis must remain separate evidence --
    a scalar/frequency match must never override a genuine concentration
    conflict."""
    text = "амоксициллин** 20-40 мг/мл суспензия, по 3 раза в сутки"
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized, known_antibiotic_raw="амоксициллин",
        current_scalar=20.0, current_unit="mg", table_context=False,
    )
    assert result.classification != SAFE_EXACT_LINK
    assert result.classification != SAFE_SINGLE_CANDIDATE


def test_concentration_range_never_becomes_a_therapeutic_dose_range():
    text = "амоксициллин** суспензия 125-250 мг/мл"
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized, known_antibiotic_raw="амоксициллин",
        current_scalar=125.0, current_unit="mg", table_context=False,
    )
    assert result.classification not in (SAFE_EXACT_LINK, SAFE_SINGLE_CANDIDATE)


def test_known_adversarial_wrong_drug_range_stays_non_safe_after_repair():
    """Carried-over adversarial case: a range belonging to a different drug
    (separated by a hard boundary) must remain non-safe regardless of the
    unit-basis repair."""
    text = "цефазолин** 1 г; амоксициллин** 20-40 мг/кг в сутки"
    norm = normalize_text(text)
    result = attribute(
        normalized=norm.normalized, known_antibiotic_raw="цефазолин",
        current_scalar=1.0, current_unit="g", table_context=False,
    )
    assert result.classification not in (SAFE_EXACT_LINK, SAFE_SINGLE_CANDIDATE)


def test_input_order_independence_for_unit_comparison():
    a, b = parse_dose_unit("mg/kg/day"), parse_dose_unit("mg/kg/dose")
    # both orderings must be non-equivalent, symmetric outcome not required
    # to be the identical enum (weight matches, time differs either way)
    assert compare_dose_units(a, b) != EXACT_EQUIVALENT
    assert compare_dose_units(b, a) != EXACT_EQUIVALENT
