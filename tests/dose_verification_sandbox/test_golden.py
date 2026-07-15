from dose_verification_sandbox.golden import run_golden, write_golden_dataset


def test_all_golden_cases_pass():
    result = run_golden()
    assert result["all_pass"], result["results"]


def test_golden_cases_labeled_calculation_verified_not_clinically_approved():
    from dose_verification_sandbox.golden import CASES
    for case in CASES:
        assert case["review_status"] == "CALCULATION_VERIFIED"
        assert case["review_status"] != "CLINICALLY_APPROVED"


def test_write_golden_dataset_file():
    path = write_golden_dataset()
    assert path.exists()
