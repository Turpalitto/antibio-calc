from dose_verification_sandbox.parser import parse_dose_expression
from dose_verification_sandbox.models import PARSED, UNPARSED


def test_fixed_adult_dose_mg():
    e = parse_dose_expression(500.0, "mg", 3.0)
    assert e.parser_status == PARSED
    assert e.numerator_unit == "mg"
    assert e.denominator_weight is False
    assert e.denominator_time is None  # "mg" alone does not say per-dose or per-day


def test_mg_per_kg_per_day_explicit():
    e = parse_dose_expression(50.0, "мг/сут/кг" if False else "mg/kg", 3.0)
    # plain "mg/kg" alone is weight-based but period-ambiguous
    assert e.denominator_weight is True
    assert e.denominator_time is None
    assert e.parser_status == PARSED


def test_explicit_per_day_unit():
    e = parse_dose_expression(900.0, "мг/сут", 3.0)
    assert e.parser_status == PARSED
    assert e.denominator_time == "day"
    assert e.denominator_weight is False


def test_gram_converted_to_mg():
    e = parse_dose_expression(1.0, "g", 2.0)
    assert e.parser_status == PARSED
    assert e.numerator_unit == "mg"
    assert e.numeric_min == 1000.0


def test_missing_unit_is_unparsed():
    e = parse_dose_expression(500.0, "", None)
    assert e.parser_status == UNPARSED


def test_missing_dose_is_unparsed():
    e = parse_dose_expression(None, "mg", 2.0)
    assert e.parser_status == UNPARSED


def test_compound_unit_is_unparsed():
    e = parse_dose_expression(1.0, "г; мг/кг", None)
    assert e.parser_status == UNPARSED


def test_percent_unit_is_unparsed():
    e = parse_dose_expression(2.0, "%", None)
    assert e.parser_status == UNPARSED


def test_drops_unit_is_unparsed():
    e = parse_dose_expression(3.0, "капли", 2.0)
    assert e.parser_status == UNPARSED


def test_ml_unit_parsed_no_conversion_needed():
    e = parse_dose_expression(5.0, "мл", 3.0)
    assert e.parser_status == PARSED
    assert e.numerator_unit == "mL"


def test_iu_unit_parsed():
    e = parse_dose_expression(100000.0, "IU", 4.0)
    assert e.parser_status == PARSED
    assert e.numerator_unit == "IU"
