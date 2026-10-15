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


def test_unit_strength_unreadable_or_liquid_without_mg_per_ml_is_a_warning() -> None:
    """The shell's unit maths (N таб на приём, D.t.d. N) reads «<N> мг» / «<N>+<M> мг» / «<N> млн ЕД»."""
    db = _db()
    db["drugs_reference"]["amoxicillin"]["forms"] = [
        {"form_type": "tablet", "concentration": "1 г"},
        {"form_type": "tablet", "concentration": "875+125 мг"},
        {"form_type": "suspension", "concentration": "250 мг/5 мл"},
    ]
    db["drugs_reference"]["benzylpenicillin_na"]["forms"] = [{"form_type": "powder_for_injection", "concentration": "1000000 ЕД"}]
    result = _validate(db)
    assert result["errors"] == []
    unreadable = [w for w in result["warnings"] if "no readable unit strength" in w]
    assert len(unreadable) == 1 and 'forms[0]: tablet concentration "1 г"' in unreadable[0], result["warnings"]
    liquid = [w for w in result["warnings"] if "without concentration_mg_per_ml" in w]
    assert len(liquid) == 1 and "forms[2]: suspension" in liquid[0], result["warnings"]


def test_combination_partner_without_its_own_regimen_is_an_error() -> None:
    """The shell doses a partner only from component_regimens[partner]; the old
    fallback printed the main drug's numbers for it."""
    db = _db()
    drug = _drug(db)
    drug.pop("drug_ref", None)
    drug["combo_ref"] = ["amoxicillin", "benzylpenicillin_na"]
    result = _validate(db)
    hits = _errors_matching(result, "component_regimens lacks a regimen for combination partner")
    assert len(hits) == 1 and '"benzylpenicillin_na"' in hits[0], result["errors"]
    drug["regimens"][0]["component_regimens"] = {"benzylpenicillin_na": {"single_dose_mg": 1000000}}
    result = _validate(db)
    assert _errors_matching(result, "component_regimens.benzylpenicillin_na needs a dose field"), result["errors"]
    drug["regimens"][0]["component_regimens"] = {"benzylpenicillin_na": {"single_dose_mg": 1000000, "freq_per_day": 4, "duration_days": "7"}}
    result = _validate(db)
    assert not [e for e in result["errors"] if "component_regimens" in e], result["errors"]


def test_route_without_a_matching_form_is_a_warning() -> None:
    """Scenario says iv, drugs_reference only has tablets: the shell falls back
    to every form and shows #route-mismatch-note; the validator says so too."""
    db = _db()
    _drug(db)["route"] = ["iv"]
    result = _validate(db)
    assert result["errors"] == []
    hits = [w for w in result["warnings"] if "has no matching form" in w]
    assert len(hits) == 1 and "forms cover: po" in hits[0]


def test_route_matching_rules_mirror_the_shell_grouping() -> None:
    """Injectable vials follow the shell: dilution.im/iv decide, a plain
    powder_for_injection without dilution serves both; combos use the union."""
    db = _db()
    db["drugs_reference"]["gentamicin"] = {
        "inn": "Гентамицин",
        "dilution": {"im": {"note": "x"}},
        "forms": [{"form_type": "powder_for_injection", "concentration": "80 мг"}],
    }
    db["drugs_reference"]["ceftriaxone"] = {
        "inn": "Цефтриаксон",
        "forms": [{"form_type": "powder_for_injection", "concentration": "1 г"}],
    }
    # a vial whose dilution block documents im only is never offered under iv
    _drug(db).update({"drug_ref": "gentamicin", "route": ["iv"]})
    assert [w for w in _validate(db)["warnings"] if "has no matching form" in w and "forms cover: im" in w]
    db["drugs_reference"]["gentamicin"]["dilution"]["iv_infusion"] = {"note": "y"}
    assert not [w for w in _validate(db)["warnings"] if "has no matching form" in w]
    # powder_for_injection without dilution serves im and iv
    _drug(db).update({"drug_ref": "ceftriaxone", "route": ["iv", "im"]})
    assert not [w for w in _validate(db)["warnings"] if "has no matching form" in w]
    # combo: the main (first) drug covers the route, the second is oral — union passes
    drug = _drug(db)
    drug.pop("drug_ref")
    drug.update({"combo_ref": ["ceftriaxone", "amoxicillin"], "route": ["iv"]})
    assert not [w for w in _validate(db)["warnings"] if "has no matching form" in w]
    # topical-only reference asked for per os → warning
    drug.pop("combo_ref")
    db["drugs_reference"]["mupirocin"] = {"inn": "Мупироцин", "forms": [{"form_type": "topical", "concentration": "2 %"}]}
    drug.update({"drug_ref": "mupirocin", "route": ["per_os"]})
    assert [w for w in _validate(db)["warnings"] if "has no matching form" in w and "forms cover: topical" in w]


def test_shipped_database_route_mismatches_are_confined_to_blocked_records() -> None:
    """Pins the current state: the 9 known route/form gaps all sit in records the
    source gate already blocks (owner queue), none in a computable record."""
    db = json.loads((ROOT / "db" / "antibio_db.json").read_text(encoding="utf-8-sig"))
    hits = [w for w in _validate(db)["warnings"] if "has no matching form" in w]
    assert hits, "rule stopped firing on the shipped DB — check validate_db.js"
    assert all(w.endswith("[blocked record]") for w in hits), [w for w in hits if not w.endswith("[blocked record]")]


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


# ---- shell-parity rules (round 6, T46) ---------------------------------------------


def _warnings_matching(result: dict, needle: str) -> list[str]:
    return [w for w in result["warnings"] if needle in w]


@pytest.mark.parametrize("value,flagged", [
    ("6 мес", False), ("18 лет", False), ("28 дней", False), ("3 нед", False), ("2 г", False),
    ("с рождения", True), ("старше 12", True), (12, True), ("грудной возраст", True),
])
def test_age_restriction_min_the_shell_cannot_parse_is_a_warning(value, flagged) -> None:
    """ageRestrictionFlag() compares only «<N> лет/мес/нед/дн» with the patient's
    age; any other wording silently degrades to a «проверьте вручную» flag."""
    db = _db()
    db["drugs_reference"]["amoxicillin"]["age_restriction_min"] = value
    result = _validate(db)
    assert result["errors"] == []
    hits = _warnings_matching(result, "age_restriction_min")
    assert bool(hits) is flagged, (value, result["warnings"])
    if flagged:
        assert "drugs_reference.amoxicillin" in hits[0] and "проверьте вручную" in hits[0]


def test_age_restriction_regex_is_the_shell_regex() -> None:
    """The validator's AGE_RESTRICTION_RE must be the literal the shell parses with,
    otherwise the rule drifts from what the screen can actually check."""
    import re

    template = (ROOT / "antibiotic_calc.html.template").read_text(encoding="utf-8")
    validator = VALIDATOR.read_text(encoding="utf-8")
    shell_fn = template[template.index("function parseAgeRestrictionDays"):]
    shell_rx = re.search(r"\.match\((/.+?/)\)", shell_fn).group(1)
    validator_rx = re.search(r"const AGE_RESTRICTION_RE = (/.+?/);", validator).group(1)
    assert shell_rx == validator_rx, (shell_rx, validator_rx)


def test_course_regex_accepts_exactly_what_the_shell_plans_a_course_for() -> None:
    """COURSE_RE (validator) is the shell's parseCourse() literal; pinned sample by sample
    so that «7 дней» / «3 недели» are planned and «однократно» / «10!» stay words."""
    import re

    template = (ROOT / "antibiotic_calc.html.template").read_text(encoding="utf-8")
    validator = VALIDATOR.read_text(encoding="utf-8")
    shell_rx = re.search(r"^const COURSE_RE = (/.+/[a-z]*);", template, re.M).group(1)
    validator_rx = re.search(r"^const COURSE_RE = (/.+/[a-z]*);", validator, re.M).group(1)
    assert shell_rx == validator_rx, (shell_rx, validator_rx)
    samples = ["7", "7-10", "7 – 10", "14–21", "0", "7 дней", "7-14 дней", "21 день", "3 сут", "3 недели", "10–12 недель",
               "хроническая", "", " 5 ", "1-", "a-b", "3 месяца", "180-365", "однократно", "10!", "7 дней (минимальный курс)"]
    script = (
        f"const a={shell_rx};"
        f"const s={json.dumps(samples, ensure_ascii=False)};"
        "console.log(JSON.stringify(s.map(x=>a.test(x.trim()))));"
    )
    completed = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    accepted = json.loads(completed.stdout)
    expected = [True, True, True, True, True, True, True, True, True, True, True,
                False, False, True, False, False, False, True, False, False, False]
    assert accepted == expected, list(zip(samples, accepted))


@pytest.mark.parametrize("value,needle", [
    ("0", "zero-day course"),
    ("14-7", "inverted range"),
    ("400", "longer than 365 days"),
    ("180-366", "longer than 365 days"),
    ("53 недели", "longer than 365 days"),
    ("7-10", None),
    ("7-10 дней", None),
    ("52 недели", None),
    (365, None),
    ("хроническая", None),
])
def test_course_sanity_zero_inverted_or_year_long_is_a_warning(value, needle) -> None:
    db = _db()
    _regimen(db)["duration_days"] = value
    result = _validate(db)
    assert result["errors"] == []
    hits = [w for w in result["warnings"] if any(k in w for k in ("zero-day", "inverted range", "longer than"))]
    if needle is None:
        assert hits == [], hits
    else:
        assert len(hits) == 1 and needle in hits[0] and f'duration_days "{value}"' in hits[0], hits


@pytest.mark.parametrize("fixed,flagged", [(3000, False), (3100, False), (2000, True), (4000, True)])
def test_single_times_frequency_disagreeing_with_fixed_daily_is_a_warning(fixed, flagged) -> None:
    """computeDose() doses from single × freq and shows dose_mg_day_fixed only as a
    cross-check («несогласованность»); the validator applies the same 5 % + 1 tolerance."""
    db = _db()
    _regimen(db)["dose_mg_day_fixed"] = fixed
    result = _validate(db)
    assert result["errors"] == []
    hits = _warnings_matching(result, "disagrees with dose_mg_day_fixed")
    assert bool(hits) is flagged, (fixed, result["warnings"])
    if flagged:
        assert f"(3000) disagrees with dose_mg_day_fixed ({fixed})" in hits[0]


def test_component_regimen_keyed_by_a_non_partner_is_a_warning() -> None:
    """A misspelt partner key is dead data: the shell ignores it and the partner is
    then reported as lacking a regimen."""
    db = _db()
    drug = _drug(db)
    drug.pop("drug_ref", None)
    drug["combo_ref"] = ["amoxicillin", "benzylpenicillin_na"]
    drug["regimens"][0]["component_regimens"] = {"benzylpenicilin_na": {"single_dose_mg": 1000000, "freq_per_day": 4}}
    result = _validate(db)
    assert _errors_matching(result, 'lacks a regimen for combination partner "benzylpenicillin_na"')
    stray = _warnings_matching(result, "is not a combination partner")
    assert len(stray) == 1 and "component_regimens.benzylpenicilin_na" in stray[0] and "partners: benzylpenicillin_na" in stray[0], result["warnings"]
    # a component regimen on a plain (non-combination) drug is equally dead
    plain = _db()
    _regimen(plain)["component_regimens"] = {"metronidazole": {"single_dose_mg": 500, "freq_per_day": 3}}
    result = _validate(plain)
    assert result["errors"] == []
    stray = _warnings_matching(result, "is not a combination partner")
    assert len(stray) == 1 and "(not a combination)" in stray[0], result["warnings"]


@pytest.mark.parametrize(
    ("note", "flagged"),
    [("Амоксициллин", True), ("  амоксициллин ", True), ("Строго 10 дней", False), ("", False), (None, False)],
)
def test_duration_note_that_only_repeats_the_drug_name_is_a_warning(note, flagged) -> None:
    """copyForMIS()/fillPrescriptionForm() print duration_note verbatim as «Указания: …»;
    a note that is just the INN tells the physician nothing (cap_adult_in_severe ceftriaxone)."""
    db = _db()
    reg = _regimen(db)
    if note is None:
        reg.pop("duration_note", None)
    else:
        reg["duration_note"] = note
    result = _validate(db)
    assert result["errors"] == []
    hits = _warnings_matching(result, "only repeats the drug name")
    assert bool(hits) is flagged, (note, result["warnings"])
    if flagged:
        assert "«Указания: …»" in hits[0] and "(owner review)" in hits[0]


@pytest.mark.parametrize(
    ("synonyms", "flagged"),
    [(["Амоксиклав", "Аугментин"], False), (None, False), ("Амоксиклав", True), (["Амоксиклав", ""], True), ([7], True)],
)
def test_drug_synonyms_must_be_an_array_of_non_empty_strings(synonyms, flagged) -> None:
    """diseaseDrugText() indexes `drugs_reference[].synonyms` (trade names) for the
    search and ignores anything that is not a non-empty string — the validator says so."""
    db = _db()
    if synonyms is not None:
        db["drugs_reference"]["amoxicillin"]["synonyms"] = synonyms
    result = _validate(db)
    assert result["errors"] == []
    hits = _warnings_matching(result, "synonyms must be an array of non-empty strings")
    assert bool(hits) is flagged, (synonyms, result["warnings"])


def test_shipped_database_has_no_shell_parity_warnings() -> None:
    db = json.loads((ROOT / "db" / "antibio_db.json").read_text(encoding="utf-8-sig"))
    result = _validate(db)
    needles = ("age_restriction_min", "is not a combination partner", "zero-day", "inverted range", "longer than 365", "disagrees with dose_mg_day_fixed")
    hits = [w for w in result["warnings"] if any(n in w for n in needles)]
    assert hits == [], hits[:5]
