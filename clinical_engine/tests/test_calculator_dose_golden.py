"""Data-driven golden cases for the shipped calculator (audit 2026-10-14, E-3/I-5).

`golden/calculator_dose_golden.json` pins, per case, the regimen exactly as it
is stored in `db/antibio_db.json` and the numbers the template must render for
a given weight: mg/day, mg per dose, the max-daily cap, ml of suspension, the
tablet/capsule wording and the ml drawn from a reconstituted vial. The JS under
test is the real template code (`computeDose`, `formatTablets`,
`computeInjectableMl`) executed in Node through the clinical-safety harness.

Two things fail this test on purpose: a change in the calculator maths and a
change in a pinned regimen. Both are clinical changes that need the
owner-physician to re-check the source before the golden is updated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clinical_engine.tests.test_calculator_clinical_safety import DB_PATH, _lit, _run

GOLDEN = Path(__file__).with_name("golden") / "calculator_dose_golden.json"
REGIMEN_FIELDS = (
    "dose_mg_kg_day", "dose_mg_kg_per_dose", "dose_mg_day_fixed",
    "single_dose_mg", "freq_per_day", "max_daily_mg",
)


def _cases() -> list[dict]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def _shipped_regimen(db: dict, case: dict) -> dict:
    record = next(r for r in db["recommendations"] if r["id"] == case["record"])
    assert record.get("calculation_blocked") is False, (
        f"{case['record']} is blocked; golden cases must target computable records"
    )
    scenario = next(s for s in record["scenarios"] if s["id"] == case["scenario"])
    line = next(l for l in scenario["lines"] if l["line_number"] == case["line_number"])
    drug = next(d for d in line["drugs"] if d["drug_ref"] == case["drug_ref"])
    matching = [r for r in drug["regimens"] if r["age_group"] == case["regimen_age_group"]]
    assert matching, f"no {case['regimen_age_group']} regimen for {case['id']}"
    return matching[case.get("regimen_index", 0)]


@pytest.fixture(scope="module")
def db() -> dict:
    return json.loads(DB_PATH.read_text(encoding="utf-8-sig"))


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_shipped_regimen_matches_the_golden_pin(db: dict, case: dict) -> None:
    regimen = _shipped_regimen(db, case)
    stored = {k: regimen.get(k) for k in REGIMEN_FIELDS if regimen.get(k) is not None}
    assert stored == case["regimen"], (
        f"{case['id']}: the shipped regimen changed — re-verify the source before updating the golden"
    )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_calculator_reproduces_the_golden_numbers(db: dict, case: dict) -> None:
    regimen = _shipped_regimen(db, case)
    body = (
        f"const reg={_lit(regimen)}; const w={case['weight_kg']}; const unit={_lit(case['unit'])};"
        "const dose=computeDose(reg,w,unit);"
        "const out={daily:dose.dailyMg,single:dose.singleMg,capped:dose.capped,"
        "inconsistent:dose.inconsistent,needWeight:dose.needWeight,unit:dose.unit};"
        f"const susp={_lit(case.get('suspension'))};"
        "if(susp){ out.single_ml=Number((dose.singleMg/susp.concentration_mg_per_ml).toFixed(2)); }"
        f"const solid={_lit(case.get('solid'))};"
        "if(solid){ out.label=formatTablets(dose.singleMg, solid); }"
        f"const inj={_lit(case.get('injectable'))};"
        "if(inj){ out.ml_text=computeInjectableMl(dose.singleMg, inj.vial); }"
        "console.log(JSON.stringify(out));"
    )
    out = _run(["computeDose", "formatTablets", "computeInjectableMl"], "", body)
    expect = case["expect"]
    assert out["needWeight"] is False
    assert out["unit"] == case["unit"]
    assert out["daily"] == pytest.approx(expect["daily"]), case["id"]
    assert out["single"] == pytest.approx(expect["single"]), case["id"]
    assert out["capped"] is expect["capped"], case["id"]
    if "inconsistent" in expect:
        assert out["inconsistent"] is expect["inconsistent"], case["id"]
    if case.get("suspension"):
        assert out["single_ml"] == pytest.approx(case["suspension"]["single_ml"]), case["id"]
    if case.get("solid"):
        assert out["label"] == case["solid"]["label"], case["id"]
    if case.get("injectable"):
        assert out["ml_text"] == case["injectable"]["ml_text"], case["id"]


def test_golden_file_covers_every_dosing_branch() -> None:
    cases = _cases()
    assert any("dose_mg_kg_day" in c["regimen"] for c in cases), "per-kg branch"
    assert any("single_dose_mg" in c["regimen"] for c in cases), "single × freq branch"
    assert any(c["expect"]["capped"] for c in cases), "max-daily cap"
    assert any(c["unit"] == "ЕД" for c in cases), "unit-based (ЕД) drug"
    assert any(c.get("suspension") for c in cases) and any(c.get("solid") for c in cases)
    assert any(c.get("injectable") for c in cases)
    assert any(c.get("solid", {}).get("form_type") == "capsule" for c in cases), "capsule rounding"
