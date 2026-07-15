"""Phase 16 — Golden Calculation Dataset.

Separate from the clinical Golden Dataset (clinical_engine/golden_cases/).
Cases here are labeled CALCULATION_VERIFIED (arithmetic correctness only),
never CLINICALLY_APPROVED. Built from synthetic fixtures because real
assembled_regimens.sqlite data currently has no cases that reach a non-BLOCKED
calculation_status (see pilot_report.json) — see
DOSE_VERIFICATION_SANDBOX_REPORT.md for why.
"""
from __future__ import annotations

import json
from pathlib import Path
from dataclasses import asdict

from .models import DoseExpression, PARSED
from .calculator import calculate

DATA_DIR = Path(__file__).parent / "data"

CASES = [
    {
        "case_id": "GC-001",
        "description": "Fixed adult dose, mg/day, 3x/day",
        "diagnosis_code": "SYNTHETIC",
        "regimen_id": None,
        "input": {"weight_kg": 70.0},
        "expr": dict(numeric_min=1500.0, numeric_max=1500.0, numerator_unit="mg",
                     denominator_weight=False, denominator_time="day", per_dose_or_per_day="day",
                     frequency=3.0, max_single_dose=None, max_daily_dose=None,
                     source_expression="1500 mg/day", parser_status=PARSED),
        "expected": {"final_max_daily_dose": 1500.0, "final_max_single_dose": 500.0},
        "tolerance": 1e-6,
        "source_reference": "synthetic fixture, not source-derived",
        "review_status": "CALCULATION_VERIFIED",
    },
    {
        "case_id": "GC-002",
        "description": "mg/kg/day, weight 18 kg, 3x/day",
        "diagnosis_code": "SYNTHETIC",
        "regimen_id": None,
        "input": {"weight_kg": 18.0},
        "expr": dict(numeric_min=50.0, numeric_max=50.0, numerator_unit="mg",
                     denominator_weight=True, denominator_time="day", per_dose_or_per_day="day",
                     frequency=3.0, max_single_dose=None, max_daily_dose=None,
                     source_expression="50 mg/kg/day", parser_status=PARSED),
        "expected": {"final_max_daily_dose": 900.0, "final_max_single_dose": 300.0},
        "tolerance": 1e-6,
        "source_reference": "synthetic fixture, not source-derived",
        "review_status": "CALCULATION_VERIFIED",
    },
    {
        "case_id": "GC-003",
        "description": "Dose range 40-60 mg/kg/day, weight 20 kg, 3x/day",
        "diagnosis_code": "SYNTHETIC",
        "regimen_id": None,
        "input": {"weight_kg": 20.0},
        "expr": dict(numeric_min=40.0, numeric_max=60.0, numerator_unit="mg",
                     denominator_weight=True, denominator_time="day", per_dose_or_per_day="day",
                     frequency=3.0, max_single_dose=None, max_daily_dose=None,
                     source_expression="40-60 mg/kg/day", parser_status=PARSED),
        "expected": {
            "final_min_daily_dose": 800.0, "final_max_daily_dose": 1200.0,
            "final_min_single_dose": 266.6666666666667, "final_max_single_dose": 400.0,
        },
        "tolerance": 1e-4,
        "source_reference": "synthetic fixture, not source-derived",
        "review_status": "CALCULATION_VERIFIED",
    },
    {
        "case_id": "GC-004",
        "description": "mg/kg/dose, weight 20 kg, 3x/day",
        "diagnosis_code": "SYNTHETIC",
        "regimen_id": None,
        "input": {"weight_kg": 20.0},
        "expr": dict(numeric_min=15.0, numeric_max=15.0, numerator_unit="mg",
                     denominator_weight=True, denominator_time="dose", per_dose_or_per_day="dose",
                     frequency=3.0, max_single_dose=None, max_daily_dose=None,
                     source_expression="15 mg/kg/dose", parser_status=PARSED),
        "expected": {"final_max_single_dose": 300.0, "final_max_daily_dose": 900.0},
        "tolerance": 1e-6,
        "source_reference": "synthetic fixture, not source-derived",
        "review_status": "CALCULATION_VERIFIED",
    },
]


def run_golden(tolerance_override: float | None = None) -> dict:
    results = []
    all_pass = True
    for case in CASES:
        expr = DoseExpression(**case["expr"])
        trace = calculate(expr, weight_kg=case["input"]["weight_kg"])
        tol = tolerance_override if tolerance_override is not None else case["tolerance"]
        mismatches = {}
        for field, expected_value in case["expected"].items():
            actual = getattr(trace, field)
            if actual is None or abs(actual - expected_value) > tol:
                mismatches[field] = {"expected": expected_value, "actual": actual}
        passed = not mismatches
        all_pass = all_pass and passed
        results.append({
            "case_id": case["case_id"],
            "description": case["description"],
            "passed": passed,
            "mismatches": mismatches,
            "review_status": case["review_status"],
        })
    return {"all_pass": all_pass, "results": results}


def write_golden_dataset() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "golden_calculation_dataset.json"
    payload = {
        "meta": {
            "label": "CALCULATION_VERIFIED — arithmetic/source-fidelity only. NOT CLINICALLY_APPROVED.",
            "distinct_from": "clinical_engine/golden_cases/ (the clinical Golden Dataset)",
        },
        "cases": CASES,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    p = write_golden_dataset()
    result = run_golden()
    print(f"Golden dataset written to {p}; all_pass={result['all_pass']}")
