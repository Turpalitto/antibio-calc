"""Rules of `db/validate_db.js` (audit 2026-10-14, finding B-3).

The validator is the only automated barrier between a disease JSON and the
physician's screen (`db/build_html.py` refuses to embed a DB that fails it).
These tests run the real Node module on small in-memory databases, so each
plausibility rule is pinned by the exact data defect it was written for.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "db" / "validate_db.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required to run db/validate_db.js")


def _validate(db: dict) -> dict:
    script = (
        "const {validateDatabase} = require(process.argv[1]);"
        "let raw='';process.stdin.on('data',c=>raw+=c);"
        "process.stdin.on('end',()=>{console.log(JSON.stringify(validateDatabase(JSON.parse(raw))));});"
    )
    completed = subprocess.run(
        [NODE, "-e", script, str(VALIDATOR)],
        input=json.dumps(db, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _db(**overrides) -> dict:
    """A minimal, fully valid computable record (one per_os tablet regimen)."""
    base = {
        "meta": {"version": "t"},
        "categories": [],
        "drugs_reference": {
            "amoxicillin": {"inn": "Амоксициллин", "forms": [{"form_type": "tablet", "concentration": "500 мг"}]},
            "benzylpenicillin_na": {"inn": "Бензилпенициллин", "dose_unit": "ЕД",
                                    "forms": [{"form_type": "powder_for_injection", "concentration": "1 млн ЕД"}]},
        },
        "recommendations": [
            {
                "id": "cap_adult",
                "name": "Пневмония",
                "mkb10": ["J18.9"],
                "cr_id": "654",
                "cr_year": 2021,
                "calculation_blocked": False,
                "source_verification_status": "CR_REFERENCE_CALCULATION",
                "scenarios": [
                    {
                        "id": "s1",
                        "name": "Нетяжёлая",
                        "age_group": "adult",
                        "lines": [
                            {
                                "line_number": 1,
                                "drugs": [
                                    {
                                        "drug_ref": "amoxicillin",
                                        "route": ["per_os"],
                                        "regimens": [
                                            {"age_group": "adult", "single_dose_mg": 1000, "freq_per_day": 3,
                                             "max_daily_mg": 3000, "duration_days": "5-7"}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def _regimen(db: dict) -> dict:
    return db["recommendations"][0]["scenarios"][0]["lines"][0]["drugs"][0]["regimens"][0]


def _drug(db: dict) -> dict:
    return db["recommendations"][0]["scenarios"][0]["lines"][0]["drugs"][0]


def _errors_matching(result: dict, needle: str) -> list[str]:
    return [e for e in result["errors"] if needle in e]


def test_minimal_valid_database_has_no_errors() -> None:
    result = _validate(_db())
    assert result["errors"] == []
    assert result["stats"]["regimens_checked"] == 1


def test_shipped_database_is_clean() -> None:
    db = json.loads((ROOT / "db" / "antibio_db.json").read_text(encoding="utf-8-sig"))
    result = _validate(db)
    assert result["errors"] == [], result["errors"][:5]
    # every record left the gate with an explicit decision
    assert all(isinstance(r.get("calculation_blocked"), bool) for r in db["recommendations"])


# ---- frequency ------------------------------------------------------------------


@pytest.mark.parametrize("freq", [8, 12, 30, 0, -1, 2.5, "3"])
def test_frequency_outside_one_to_six_blocks_a_computable_record(freq) -> None:
    db = _db()
    _regimen(db)["freq_per_day"] = freq
    result = _validate(db)
    assert _errors_matching(result, "freq_per_day"), result


def test_missing_frequency_blocks() -> None:
    db = _db()
    del _regimen(db)["freq_per_day"]
    assert _errors_matching(_validate(db), "missing freq_per_day")


# ---- dose presence / plausibility ---------------------------------------------------


def test_regimen_without_any_dose_field_blocks_unless_topical() -> None:
    db = _db()
    reg = _regimen(db)
    for key in ("single_dose_mg", "max_daily_mg"):
        reg.pop(key, None)
    assert _errors_matching(_validate(db), "no dose field")
    topical = _db()
    treg = _regimen(topical)
    for key in ("single_dose_mg", "max_daily_mg"):
        treg.pop(key, None)
    _drug(topical)["route"] = ["topical"]
    assert not _errors_matching(_validate(topical), "no dose field")


@pytest.mark.parametrize("field,value", [
    ("dose_mg_kg_day", 1000),        # 1 g/kg/day
    ("dose_mg_kg_per_dose", 500),
    ("dose_mg_day_fixed", 50000),
    ("single_dose_mg", 10000),
    ("max_daily_mg", 100000),
    ("single_dose_mg", 0),
    ("single_dose_mg", -5),
    ("single_dose_mg", "1000"),
])
def test_implausible_or_non_numeric_dose_blocks(field, value) -> None:
    db = _db()
    _regimen(db)[field] = value
    assert _errors_matching(_validate(db), field), (field, value)


def test_unit_consistency_flags_milligram_sized_values_on_a_units_drug() -> None:
    db = _db()
    drug = _drug(db)
    drug["drug_ref"] = "benzylpenicillin_na"
    drug["route"] = ["iv"]
    drug["regimens"] = [{"age_group": "adult", "single_dose_mg": 500, "freq_per_day": 4}]
    result = _validate(db)
    assert _errors_matching(result, "implausibly small")
    drug["regimens"] = [{"age_group": "adult", "single_dose_mg": 2000000, "freq_per_day": 4, "max_daily_mg": 24000000}]
    assert _validate(db)["errors"] == []


def test_child_mg_kg_regimen_without_ceiling_is_a_warning_not_an_error() -> None:
    db = _db()
    db["recommendations"][0]["scenarios"][0]["age_group"] = "child"
    _drug(db)["regimens"] = [{"age_group": "child", "dose_mg_kg_day": 45, "freq_per_day": 3}]
    result = _validate(db)
    assert result["errors"] == []
    assert any("without max_daily_mg" in w for w in result["warnings"])


# ---- structure -------------------------------------------------------------------


def test_empty_route_blocks_a_computable_record() -> None:
    db = _db()
    _drug(db)["route"] = []
    assert _errors_matching(_validate(db), "route is empty")


def test_unknown_route_age_group_and_form_type_block() -> None:
    db = _db()
    _drug(db)["route"] = ["sublingual"]
    _regimen(db)["age_group"] = "teen"
    db["drugs_reference"]["amoxicillin"]["forms"][0]["form_type"] = "lozenge"
    result = _validate(db)
    assert _errors_matching(result, 'unknown route "sublingual"')
    assert _errors_matching(result, 'age_group "teen"')
    assert _errors_matching(result, 'unknown form_type "lozenge"')


def test_comma_joined_mkb_string_blocks() -> None:
    db = _db()
    db["recommendations"][0]["mkb10"] = ["D82.3, D82.8, D84.8"]
    assert _errors_matching(_validate(db), "comma-joined")
    db["recommendations"][0]["mkb10"] = ["D82.3", "D82.8", "B20-B24", "B20-24"]
    assert _validate(db)["errors"] == []


def test_dangling_drug_reference_blocks() -> None:
    db = _db()
    _drug(db)["drug_ref"] = "vancomycin"
    assert _errors_matching(_validate(db), 'drug_ref "vancomycin" NOT FOUND')


def test_duplicate_ids_block() -> None:
    db = _db()
    db["recommendations"].append(copy.deepcopy(db["recommendations"][0]))
    assert _errors_matching(_validate(db), "duplicate id")


# ---- provenance / gate ------------------------------------------------------------------


def test_record_without_gate_decision_blocks() -> None:
    db = _db()
    del db["recommendations"][0]["calculation_blocked"]
    del db["recommendations"][0]["source_verification_status"]
    result = _validate(db)
    assert _errors_matching(result, "calculation_blocked must be an explicit boolean")
    assert _errors_matching(result, "missing source_verification_status")


def test_computable_record_without_cr_or_basis_blocks_but_blocked_record_passes() -> None:
    db = _db()
    rec = db["recommendations"][0]
    rec["cr_id"] = "—"
    rec["source_verification_status"] = "NO_FEDERAL_CR_EXPERT_BASIS"
    assert _errors_matching(_validate(db), "neither a federal cr_id nor a documented basis")
    rec["cr_note"] = "СКАТ 2018, IDSA 2019"
    assert _validate(db)["errors"] == []
    rec.pop("cr_note")
    rec["calculation_blocked"] = True
    rec["calculation_block_reason"] = "нет источника"
    rec["source_verification_status"] = "SOURCE_BASIS_MISSING"
    assert _validate(db)["errors"] == []


def test_non_cr_record_labelled_cr_reference_blocks() -> None:
    db = _db()
    rec = db["recommendations"][0]
    rec["cr_id"] = "—"
    rec["cr_note"] = "IDSA"
    rec["source_verification_status"] = "CR_REFERENCE_CALCULATION"
    assert _errors_matching(_validate(db), "not a federal CR id but status says CR_REFERENCE_CALCULATION")


def test_blocked_record_defects_are_warnings_not_errors() -> None:
    """A blocked record cannot compute; its regimen defects must not sink the build."""
    db = _db()
    rec = db["recommendations"][0]
    rec["calculation_blocked"] = True
    rec["calculation_block_reason"] = "pending physician review"
    rec["source_verification_status"] = "EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW"
    _regimen(db)["freq_per_day"] = 8
    _regimen(db)["single_dose_mg"] = 1.0
    _drug(db)["route"] = []
    result = _validate(db)
    assert result["errors"] == []
    assert any("freq_per_day=8" in w for w in result["warnings"])
    assert any("route is empty" in w for w in result["warnings"])


def test_blocked_record_without_reason_blocks() -> None:
    db = _db()
    db["recommendations"][0]["calculation_blocked"] = True
    assert _errors_matching(_validate(db), "without calculation_block_reason")


def test_unknown_status_blocks() -> None:
    db = _db()
    db["recommendations"][0]["source_verification_status"] = "SOURCE_PDF_VERIFIED"
    assert _errors_matching(_validate(db), "unknown source_verification_status")


def test_cli_db_flag_and_exit_codes(tmp_path) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_db(), ensure_ascii=False), encoding="utf-8")
    bad_db = _db()
    _regimen(bad_db)["freq_per_day"] = 12
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(bad_db, ensure_ascii=False), encoding="utf-8")
    ok = subprocess.run([NODE, str(VALIDATOR), "--db", str(good), "--json"], capture_output=True, text=True)
    assert ok.returncode == 0 and json.loads(ok.stdout)["ok"] is True
    ko = subprocess.run([NODE, str(VALIDATOR), "--db", str(bad), "--json"], capture_output=True, text=True)
    assert ko.returncode == 1 and json.loads(ko.stdout)["errors"] == 1
    missing = subprocess.run([NODE, str(VALIDATOR), "--db", str(tmp_path / "nope.json"), "--json"], capture_output=True, text=True)
    assert missing.returncode == 2
