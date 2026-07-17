"""RC-030 Part III targeted-recovery pilot — safety invariant tests.

Covers what's testable without a real human reviewer or real compute
session: the fail-closed guarantees of validation_unit.py and
precision_calculator.py, and the range-expression RCA's core claim.
"""
import pytest

from dose_verification_sandbox.validation_unit import DoseSemanticEvidenceUnit
from dose_verification_sandbox.precision_calculator import compute_precision, wilson_interval, MIN_SAMPLE_SIZE
from dose_verification_sandbox.validation_status import TYPES_MEETING_PRECISION_THRESHOLD


def _unit_kwargs(**overrides):
    base = dict(
        unit_id="u1", regimen_id="5574", regimen_version=1, antibiotic="x", diagnosis="x",
        dose_token="50", dose_token_start=0, dose_token_end=2,
        source_semantic_marker=None, marker_start=None, marker_end=None,
        source_quote="...", sentence_boundary=None, alternative_boundary=None,
        table_row=None, table_column=None, frequency=None, route=None,
        source_pdf="x.pdf", source_page="1", provenance="p",
        parser_semantic_type="WEIGHT_PER_DAY", parser_rule_id="r1", parser_confidence=0.9,
    )
    base.update(overrides)
    return base


def test_evidence_unit_defaults_to_unvalidated_blocked():
    u = DoseSemanticEvidenceUnit(**_unit_kwargs())
    assert u.validation_status == "UNVALIDATED"
    assert u.calculation_eligibility == "BLOCKED"


def test_evidence_unit_rejects_non_blocked_eligibility():
    with pytest.raises(ValueError):
        DoseSemanticEvidenceUnit(**_unit_kwargs(calculation_eligibility="QA_ELIGIBLE"))


def test_evidence_unit_rejects_invalid_human_fidelity_verdict():
    with pytest.raises(ValueError):
        DoseSemanticEvidenceUnit(**_unit_kwargs(human_fidelity_verdict="NOT_A_REAL_VERDICT"))


def test_evidence_unit_accepts_valid_human_fidelity_verdict():
    # Note: DoseSemanticEvidenceUnit's taxonomy (CORRECT_EXPLICIT_PER_DAY, ...)
    # was reconciled as the canonical one in RC030_VERDICT_TAXONOMY_DECISION.md;
    # the owner-review interface's UI action labels (SOURCE_CONFIRMS_PER_DAY, ...)
    # map onto it via dose_verification_sandbox.verdict_taxonomy — see
    # test_owner_pilot_consolidation.py.
    u = DoseSemanticEvidenceUnit(**_unit_kwargs(human_fidelity_verdict="CORRECT_EXPLICIT_PER_DAY"))
    assert u.human_fidelity_verdict == "CORRECT_EXPLICIT_PER_DAY"
    # even with a confirming verdict recorded, eligibility still defaults to BLOCKED
    assert u.calculation_eligibility == "BLOCKED"


def test_wilson_interval_matches_known_reference_value():
    # 15/15 perfect score — cited in RC030_EVIDENCE_VALIDATION_REPORT.md as
    # capping the provable lower bound "around 80%" even at a perfect small sample.
    lower, upper = wilson_interval(15, 15)
    assert 0.79 < lower < 0.80
    assert upper == 1.0


def test_precision_excludes_ambiguous_from_denominator():
    verdicts = (
        [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 10
        + [{"verdict": "WRONG_DOSE_ANCHOR"}] * 2
        + [{"verdict": "REMAINS_AMBIGUOUS"}] * 5
    )
    result = compute_precision("WEIGHT_PER_DAY", verdicts)
    assert result.reviewed_count == 17
    assert result.correct_count == 10
    assert result.incorrect_count == 2
    assert result.ambiguous_count == 5
    # denominator is correct+incorrect only, never inflated by ambiguous
    assert result.precision == pytest.approx(10 / 12)


def test_precision_below_min_sample_flagged_unreliable():
    verdicts = [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 5
    result = compute_precision("WEIGHT_PER_DOSE", verdicts)
    assert result.reviewed_count < MIN_SAMPLE_SIZE
    assert result.sample_size_reliable is False


def test_precision_calculator_never_touches_threshold_set():
    before = set(TYPES_MEETING_PRECISION_THRESHOLD)
    compute_precision("WEIGHT_PER_DAY", [{"verdict": "CORRECT_EXPLICIT_PER_DAY"}] * 50)
    assert TYPES_MEETING_PRECISION_THRESHOLD == before
    assert TYPES_MEETING_PRECISION_THRESHOLD == set()


def test_range_collapse_reproducible_on_known_regimen():
    """Reproduces the RC030_RANGE_EXPRESSION_RCA.md finding as a regression
    test: parse_dose_expression only ever receives a scalar `dose`, so
    numeric_min == numeric_max always, and is_range can never be True."""
    from dose_verification_sandbox.parser import parse_dose_expression

    expr = parse_dose_expression(20.0, "mg/kg", 2.0)
    assert expr.numeric_min == expr.numeric_max == 20.0


def test_dose_normalizer_drops_range_upper_bound():
    """Reproduces RC030_RANGE_LOSS_STAGE_RCA.md's exact finding:
    medical_normalizer.drug_parser.DoseNormalizer's regex captures a range's
    upper bound in match.group(2), but parse() only ever reads group(1) —
    the upper bound is silently discarded before RC-030 ever sees the data.
    This is a regression test pinning the current (buggy) behavior, not an
    endorsement of it — see the RCA for the proposed normalizer-layer fix,
    not implemented in this turn."""
    from medical_normalizer.drug_parser import DoseNormalizer
    from medical_normalizer.models import NormalizedRegimen

    cases = [("20-50", 20.0), ("20–50", 20.0), ("500 - 1000", 500.0), ("50-80", 50.0)]
    for raw_dose, expected_value in cases:
        regimen = NormalizedRegimen()
        DoseNormalizer.parse(regimen, {"dose": raw_dose, "unit": "mg/kg"})
        assert regimen.dose_value == expected_value, f"input {raw_dose!r} unexpectedly changed behavior"
