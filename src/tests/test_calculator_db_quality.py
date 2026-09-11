"""Data-quality invariants for the shipped calculator database.

These are regression guards for defects found in the 2026-09-10 audit. Each one
pins a concrete failure that already shipped once:

* ``mkb10`` entries holding comma-joined code lists (``"C83.5, C91.0"``) — 16
  nozologies in ``extended_dosa``, silently invisible to every ICD-10 join;
* ``mkb10`` block ranges (``"B20-24"``) stored as a single token;
* duplicate disease / scenario identifiers;
* regimens with no dose at all sitting on a nozology whose calculation is open;
* a КР crosswalk whose ``purpose`` is anything but navigation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.pipeline.extraction.icd10 import expand_mkb_range, is_valid_mkb, mkb_prefix, normalize_mkb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "db" / "antibio_db.json"
DISEASES_DIR = ROOT / "db" / "diseases"

ICD10 = re.compile(r"^[A-Z]\d{2}(\.\d{1,3})?$")
CALCULABLE_ROUTES = {"per_os", "iv", "im"}


@pytest.fixture(scope="module")
def db() -> dict:
    return json.loads(DB_PATH.read_text(encoding="utf-8-sig"))


# ── shared МКБ-10 helper ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["A00.0"], ["A00.0"]),
        ("A00.0", ["A00.0"]),
        (["C83.5, C91.0, C95.0"], ["C83.5", "C91.0", "C95.0"]),
        (["A01; A02"], ["A01", "A02"]),
        (["B20-24"], ["B20", "B21", "B22", "B23", "B24"]),
        (["b20–b24"], ["B20", "B21", "B22", "B23", "B24"]),
        (["A01", "a01"], ["A01"]),
        (None, []),
        ([None, "", "  "], []),
    ],
)
def test_normalize_mkb(raw, expected):
    assert normalize_mkb(raw) == expected


@pytest.mark.parametrize(
    "token,expected",
    [
        ("B20-24", ["B20", "B21", "B22", "B23", "B24"]),
        ("A99-B01", ["A99-B01"]),  # crosses a letter: not expanded, not invented
        ("B24-20", ["B24-20"]),  # backwards: not expanded
        ("A00", ["A00"]),
    ],
)
def test_expand_mkb_range(token, expected):
    assert expand_mkb_range(token) == expected


@pytest.mark.parametrize(
    "code,valid",
    [("A00", True), ("A00.0", True), ("A00.00", True), ("a00", True), ("B20-24", False), ("", False), ("123", False)],
)
def test_is_valid_mkb(code, valid):
    assert is_valid_mkb(code) is valid


def test_mkb_prefix():
    assert mkb_prefix("A01.23") == "A01"
    assert mkb_prefix("a01") == "A01"


# ── shipped database ────────────────────────────────────────────────────────


def test_every_mkb10_entry_is_a_single_well_formed_code(db):
    bad = [
        (rec["id"], code)
        for rec in db["recommendations"]
        for code in rec.get("mkb10") or []
        if not ICD10.match(str(code).strip())
    ]
    assert bad == [], f"malformed ICD-10 codes: {bad[:5]}"


def test_source_disease_files_also_hold_single_codes():
    """Guards the input files, not just the build output."""
    bad = []
    for path in sorted(DISEASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for rec in data.get("recommendations", []):
            for code in rec.get("mkb10") or []:
                if not is_valid_mkb(code):
                    bad.append((path.name, rec.get("id"), code))
    assert bad == [], bad[:5]


def test_no_duplicate_disease_ids(db):
    ids = [rec["id"] for rec in db["recommendations"]]
    assert len(ids) == len(set(ids))


def test_no_duplicate_scenario_ids_within_a_disease(db):
    offenders = []
    for rec in db["recommendations"]:
        ids = [sc.get("id") for sc in rec.get("scenarios") or []]
        if len(ids) != len(set(ids)):
            offenders.append(rec["id"])
    assert offenders == []


def test_every_dose_bearing_regimen_has_a_frequency(db):
    missing = [
        (rec["id"], drug.get("drug_ref"))
        for rec in db["recommendations"]
        for sc in rec.get("scenarios") or []
        for ln in sc.get("lines") or []
        for drug in ln.get("drugs") or []
        for reg in drug.get("regimens") or []
        if not reg.get("freq_per_day")
    ]
    assert missing == []


def test_uncalculable_regimens_only_exist_on_blocked_nosologies(db):
    """A dose-less regimen on an open disease would render a zero dose."""
    offenders = []
    for rec in db["recommendations"]:
        if rec.get("calculation_blocked"):
            continue
        for sc in rec.get("scenarios") or []:
            for ln in sc.get("lines") or []:
                for drug in ln.get("drugs") or []:
                    for reg in drug.get("regimens") or []:
                        if (
                            reg.get("dose_mg_kg_day") is None
                            and reg.get("dose_mg_day_fixed") is None
                            and reg.get("single_dose_mg") is None
                        ):
                            offenders.append((rec["id"], drug.get("drug_ref")))
    assert offenders == []


def test_single_dose_times_frequency_never_exceeds_the_daily_maximum(db):
    """Guards the "silent underdose" class fixed in the July 2026 audit."""
    offenders = []
    for rec in db["recommendations"]:
        for sc in rec.get("scenarios") or []:
            for ln in sc.get("lines") or []:
                for drug in ln.get("drugs") or []:
                    for reg in drug.get("regimens") or []:
                        single, freq, cap = (
                            reg.get("single_dose_mg"),
                            reg.get("freq_per_day"),
                            reg.get("max_daily_mg"),
                        )
                        if isinstance(single, (int, float)) and isinstance(freq, (int, float)) and isinstance(cap, (int, float)):
                            if single * freq > cap * 1.0001:
                                offenders.append((rec["id"], drug.get("drug_ref"), single, freq, cap))
    assert offenders == [], offenders[:5]


def test_routes_are_calculable_or_explicitly_flagged(db):
    unknown = [
        (rec["id"], drug.get("drug_ref"), route)
        for rec in db["recommendations"]
        for sc in rec.get("scenarios") or []
        for ln in sc.get("lines") or []
        for drug in ln.get("drugs") or []
        for route in drug.get("route") or []
        if route not in CALCULABLE_ROUTES | {"topical"}
    ]
    assert unknown == []


def test_every_drug_ref_resolves_in_drugs_reference(db):
    reference = {key for key in db["drugs_reference"] if key != "_note"}
    used = set()
    for rec in db["recommendations"]:
        for sc in rec.get("scenarios") or []:
            for ln in sc.get("lines") or []:
                for drug in ln.get("drugs") or []:
                    if drug.get("drug_ref"):
                        used.add(drug["drug_ref"])
                    used.update(drug.get("combo_ref") or [])
    assert used - reference == set()


# ── КР crosswalk embedding ──────────────────────────────────────────────────


def test_crosswalk_summary_is_navigation_only_and_internally_consistent(db):
    summary = db["meta"]["guideline_crosswalk"]
    assert summary["purpose"] == "NAVIGATION_ONLY"
    assert summary["content_sha256"].startswith("sha256:")
    assert summary["confidence_by_method"] == {
        "ICD10_EXACT": "HIGH",
        "ICD10_BLOCK": "MEDIUM",
        "TITLE_EXACT": "LOW",
    }
    links = [link for rec in db["recommendations"] for link in rec.get("guideline_links") or []]
    linked_diseases = {rec["id"] for rec in db["recommendations"] if rec.get("guideline_links")}
    assert len(links) == summary["links"]
    assert len(linked_diseases) == summary["linked_diseases"]


def test_guideline_links_reference_guidelines_that_exist_in_the_corpus(db):
    index = json.loads(
        (ROOT / "clinical_engine" / "resources" / "diagnosis_index.json").read_text(encoding="utf-8-sig")
    )
    corpus_ids = {entry["guideline_id"] for entry in index["entries"]}
    corpus_titles = {entry["guideline_title"] for entry in index["entries"]}
    for rec in db["recommendations"]:
        for link in rec.get("guideline_links") or []:
            assert link["guideline_id"] in corpus_ids, link
            assert link["title"] in corpus_titles, link


def test_crosswalk_never_marks_anything_as_approved_or_unblocks(db):
    """The navigation layer must not weaken the source gate."""
    for rec in db["recommendations"]:
        assert "approved" not in rec, rec["id"]
        assert "physician_approved" not in rec, rec["id"]
    blocked = [rec for rec in db["recommendations"] if rec.get("calculation_blocked")]
    with_links_and_open = [
        rec["id"]
        for rec in db["recommendations"]
        if rec.get("guideline_links")
        and not rec.get("calculation_blocked")
        and rec.get("source_verification_status") != "CALCULATOR_BOUND_VERIFIED"
    ]
    assert with_links_and_open == []
    assert len(blocked) >= 100  # the gate is still fail-closed at scale


def test_validate_db_js_reports_no_errors():
    """The Node gate is the build's own check — run it, do not re-implement it."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    completed = subprocess.run(
        [node, str(ROOT / "db" / "validate_db.js")], capture_output=True, text=True, cwd=ROOT
    )
    assert completed.returncode == 0, completed.stdout[-4000:]
    assert "ERROR" not in completed.stdout


# ── единицы разведения против dose_unit препарата ────────────────────────────


def _node():
    import shutil

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    return node


def _run_validator(db_payload, tmp_path):
    import subprocess

    candidate = tmp_path / "candidate_db.json"
    candidate.write_text(json.dumps(db_payload, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [_node(), str(ROOT / "db" / "validate_db.js"), str(candidate)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def _dilution_errors(stdout: str) -> list[str]:
    return [line.strip() for line in stdout.splitlines() if "final_concentration" in line]


def test_shipped_db_keeps_dilution_units_consistent_with_dose_unit():
    """Инвариант: концентрация флакона выражена в той же единице, что доза препарата.

    Калькулятор считает ``singleMg / final_concentration_*_ml``, беря то поле,
    которое присутствует, поэтому флакон в мг/мл у препарата в ЕД молча дал бы
    неверный объём — тот же класс путаницы единиц, из-за которого метки
    бензилпенициллина читались как «4000000 мг».
    """
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    refs = db.get("drugs_reference") or {}

    checked = 0
    for key, ref in refs.items():
        if not isinstance(ref, dict) or key == "_note":
            continue
        dose_unit = ref.get("dose_unit") or "мг"
        for route, route_data in (ref.get("dilution") or {}).items():
            if not isinstance(route_data, dict):
                continue
            for vial in route_data.get("solvent_options") or []:
                has_mg = vial.get("final_concentration_mg_ml") is not None
                has_units = vial.get("final_concentration_units_ml") is not None
                if not (has_mg or has_units):
                    continue
                checked += 1
                assert not (has_mg and has_units), f"{key}/{route}: указаны оба поля концентрации"
                if has_mg:
                    assert dose_unit == "мг", f"{key}/{route}: мг/мл у препарата в {dose_unit}"
                else:
                    assert dose_unit != "мг", f"{key}/{route}: ЕД/мл у препарата в мг"

    assert checked >= 80, f"ожидалось не менее 80 опций с концентрацией, получено {checked}"


def test_validator_rejects_mg_vial_for_a_unit_dosed_drug(tmp_path):
    """Проверка обязана быть живой: ловим намеренно испорченные данные."""
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    vial = db["drugs_reference"]["benzylpenicillin_na"]["dilution"]["iv_bolus"]["solvent_options"][0]
    vial["final_concentration_mg_ml"] = vial.pop("final_concentration_units_ml")

    result = _run_validator(db, tmp_path)

    assert result.returncode == 1, result.stdout[-2000:]
    errors = _dilution_errors(result.stdout)
    assert len(errors) == 1
    assert "dosed in ЕД" in errors[0]


def test_validator_rejects_units_vial_for_a_mg_drug(tmp_path):
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    vial = db["drugs_reference"]["amoxiclav"]["dilution"]["iv_infusion"]["solvent_options"][0]
    vial["final_concentration_units_ml"] = vial.pop("final_concentration_mg_ml")

    result = _run_validator(db, tmp_path)

    assert result.returncode == 1
    errors = _dilution_errors(result.stdout)
    assert len(errors) == 1
    assert "dosed in мг" in errors[0]


def test_validator_rejects_both_concentration_fields(tmp_path):
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    vial = db["drugs_reference"]["amoxiclav"]["dilution"]["iv_infusion"]["solvent_options"][0]
    vial["final_concentration_units_ml"] = 40

    result = _run_validator(db, tmp_path)

    assert result.returncode == 1
    errors = _dilution_errors(result.stdout)
    assert len(errors) == 1
    assert "cannot tell which to divide by" in errors[0]


def test_validator_rejects_non_positive_concentration(tmp_path):
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    db["drugs_reference"]["amoxiclav"]["dilution"]["iv_infusion"]["solvent_options"][0][
        "final_concentration_mg_ml"
    ] = 0

    result = _run_validator(db, tmp_path)

    assert result.returncode == 1
    errors = _dilution_errors(result.stdout)
    assert len(errors) == 1
    assert "must be positive" in errors[0]


def test_validator_accepts_the_shipped_db_via_explicit_path(tmp_path):
    """Явный путь — не обход проверки, а способ её протестировать."""
    result = _run_validator(json.loads(DB_PATH.read_text(encoding="utf-8-sig")), tmp_path)

    assert result.returncode == 0, result.stdout[-2000:]
    assert _dilution_errors(result.stdout) == []


# ── базис дозы против композитной таблетки ────────────────────────────────────


def test_composite_tablet_basis_mismatch_is_found_exactly_once():
    """Измерено: ровно один режим в БД расходится по базису с формой.

    ``uti_prophylaxis`` / ко-тримоксазол: 480 мг — это ровно одна таблетка
    «400+80 мг» (400 сульфаметоксазол + 80 триметоприм), но калькулятор делит на
    первый компонент (``parseFloat`` останавливается на «+»), поэтому печатает
    «1.2 таб». Оба числа настоящие, расходятся только базисы — и больше в цепочке
    это некому заметить.
    """
    import subprocess

    completed = subprocess.run(
        [_node(), str(ROOT / "db" / "validate_db.js")], capture_output=True, text=True, cwd=ROOT
    )
    hits = [line.strip() for line in completed.stdout.splitlines() if "whole number of" in line]

    assert len(hits) == 1, f"ожидался ровно один случай, получено {len(hits)}: {hits}"
    assert "uti_prophylaxis" in hits[0]
    assert "cotrimoxazole" in hits[0]
    assert "1.2 tablets" in hits[0]


def test_validator_escalates_composite_basis_mismatch_to_error_on_an_open_disease(tmp_path):
    """Тот же дефект на открытой нозологии — уже ERROR, а не предупреждение."""
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    target = next(r for r in db["recommendations"] if r["id"] == "uti_prophylaxis")
    target["calculation_blocked"] = False

    result = _run_validator(db, tmp_path)

    assert result.returncode == 1, result.stdout[-2000:]
    errors = [line.strip() for line in result.stdout.splitlines() if "ERROR" in line and "whole number of" in line]
    assert len(errors) == 1


def test_validator_does_not_flag_doses_consistent_with_the_first_component(tmp_path):
    """800 мг против «800+160 мг» — ровно одна таблетка по первому компоненту."""
    import subprocess

    completed = subprocess.run(
        [_node(), str(ROOT / "db" / "validate_db.js")], capture_output=True, text=True, cwd=ROOT
    )
    hits = [line.strip() for line in completed.stdout.splitlines() if "whole number of" in line]

    # Единственный найденный случай — 480 мг; режим «800/160 мг 2 р/д» не flagged.
    assert all("800/160" not in h for h in hits), hits


# ── концентрация пероральной жидкости против dose_unit ────────────────────────


def test_oral_liquid_concentrations_match_the_drug_unit():
    """Пероральная ветка делит дозу на ``concentration_mg_per_ml`` без проверки.

    Замер по shipped-БД: 26 жидких форм с концентрацией, ни одной у препарата
    не в мг. Инвариант закрепляется, а не чинится — дефекта сейчас нет.
    """
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    refs = db.get("drugs_reference") or {}

    checked = 0
    for key, ref in refs.items():
        if not isinstance(ref, dict) or key == "_note":
            continue
        dose_unit = ref.get("dose_unit") or "мг"
        for form in ref.get("forms") or []:
            conc = form.get("concentration_mg_per_ml")
            if conc is None:
                continue
            checked += 1
            assert conc > 0, f"{key}: concentration_mg_per_ml = {conc}"
            assert dose_unit == "мг", f"{key}: жидкая форма в мг/мл у препарата в {dose_unit}"

    assert checked >= 20, f"ожидалось не менее 20 жидких форм с концентрацией, получено {checked}"


def test_validator_rejects_oral_liquid_on_a_unit_dosed_drug(tmp_path):
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    db["drugs_reference"]["benzylpenicillin_na"]["forms"].append(
        {
            "form_type": "suspension",
            "concentration": "100000 ЕД/5 мл",
            "concentration_mg_per_ml": 20000,
        }
    )

    result = _run_validator(db, tmp_path)

    assert result.returncode == 1, result.stdout[-2000:]
    hits = [line.strip() for line in result.stdout.splitlines() if "concentration_mg_per_ml" in line]
    assert len(hits) == 1, hits
    assert "dosed in ЕД" in hits[0]


def test_validator_rejects_non_positive_oral_concentration(tmp_path):
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    for form in db["drugs_reference"]["amoxicillin"]["forms"]:
        if form.get("concentration_mg_per_ml") is not None:
            form["concentration_mg_per_ml"] = 0
            break

    result = _run_validator(db, tmp_path)

    assert result.returncode == 1
    hits = [line.strip() for line in result.stdout.splitlines() if "concentration_mg_per_ml" in line]
    assert len(hits) == 1, hits
    assert "must be positive" in hits[0]
