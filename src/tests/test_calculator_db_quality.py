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


# ── component_regimens против combo_ref ───────────────────────────────────────


def test_component_regimens_keys_are_all_real_components():
    """Ключ ``component_regimens`` обязан быть компонентом этой записи.

    Ключ вне ``combo_ref`` называет препарат, которого в записи нет, и был бы
    молча проигнорирован всеми путями отрисовки. Замер: 16 комбинаций,
    16 режимов с ``component_regimens``, 0 посторонних ключей.
    """
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))

    combos = 0
    with_cr = 0
    stray: list[str] = []
    for rec in db["recommendations"]:
        for scenario in rec.get("scenarios") or []:
            for line in scenario.get("lines") or []:
                for drug in line.get("drugs") or []:
                    refs = drug.get("combo_ref") or ([drug["drug_ref"]] if drug.get("drug_ref") else [])
                    if drug.get("combo_ref"):
                        combos += 1
                    for regimen in drug.get("regimens") or []:
                        cr = regimen.get("component_regimens")
                        if not cr:
                            continue
                        with_cr += 1
                        for key in cr:
                            if key not in refs:
                                stray.append(f"{rec['id']}: {key} not in {refs}")

    assert combos >= 10, combos
    assert with_cr >= 10, with_cr
    assert stray == [], stray


def test_validator_rejects_a_stray_component_regimen_key(tmp_path):
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    mutated = False
    for rec in db["recommendations"]:
        if mutated:
            break
        for scenario in rec.get("scenarios") or []:
            if mutated:
                break
            for line in scenario.get("lines") or []:
                if mutated:
                    break
                for drug in line.get("drugs") or []:
                    if not drug.get("combo_ref") or not drug.get("regimens"):
                        continue
                    drug["regimens"][0].setdefault("component_regimens", {})["azithromycin"] = {
                        "single_dose_mg": 500
                    }
                    mutated = True
                    break
    assert mutated, "в БД не нашлось комбинации с режимами"

    result = _run_validator(db, tmp_path)

    assert result.returncode == 1, result.stdout[-2000:]
    hits = [line.strip() for line in result.stdout.splitlines() if "component_regimens key" in line]
    assert len(hits) == 1, hits
    assert "azithromycin" in hits[0]


def test_validator_warns_on_a_combination_without_component_regimens(tmp_path):
    """Без собственных режимов все компоненты наследуют режим линии — это надо видеть."""
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    mutated = False
    for rec in db["recommendations"]:
        if mutated:
            break
        for scenario in rec.get("scenarios") or []:
            if mutated:
                break
            for line in scenario.get("lines") or []:
                if mutated:
                    break
                for drug in line.get("drugs") or []:
                    if not drug.get("combo_ref") or len(drug["combo_ref"]) < 2:
                        continue
                    for regimen in drug.get("regimens") or []:
                        regimen.pop("component_regimens", None)
                    mutated = True
                    break
    assert mutated, "в БД не нашлось многокомпонентной комбинации"

    result = _run_validator(db, tmp_path)

    hits = [line.strip() for line in result.stdout.splitlines() if "no component_regimens" in line]
    assert len(hits) >= 1, result.stdout[-2000:]


# ── проекция кроссволка в БД против артефакта-источника ───────────────────────

_CROSSWALK_ARTIFACT = (
    ROOT / "clinical_engine" / "resources" / "calculator_crosswalk.json"
)


def test_db_crosswalk_projection_matches_the_source_artifact():
    """Числа в ``meta.guideline_crosswalk`` обязаны совпадать с артефактом.

    Проекцию в БД и артефакт ``calculator_crosswalk.json`` собирают разные шаги
    (``db/build_db.py`` и ``python -m clinical_engine.crosswalk``). Если пересобрать
    одно и забыть другое, панель в HTML станет показывать устаревшие числа, и ни
    один существующий тест этого не поймает: каждый сверял проекцию саму с собой.
    """
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    artifact = json.loads(_CROSSWALK_ARTIFACT.read_text(encoding="utf-8-sig"))

    projection = db["meta"]["guideline_crosswalk"]
    coverage = artifact["meta"]["coverage"]

    for key in (
        "calculator_diseases",
        "linked_diseases",
        "unmatched_diseases",
        "linked_guidelines",
        "links",
        "links_by_method",
    ):
        assert projection[key] == coverage[key], f"{key}: {projection[key]} != {coverage[key]}"

    assert projection["content_sha256"] == artifact["content_sha256"]
    assert projection["purpose"] == artifact["meta"]["purpose"] == "NAVIGATION_ONLY"
    assert projection["confidence_by_method"] == artifact["meta"]["confidence_by_method"]


def test_every_coverage_number_is_backed_by_the_actual_data():
    """Заявленные числа — не декларация: каждое пересчитывается из данных."""
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    artifact = json.loads(_CROSSWALK_ARTIFACT.read_text(encoding="utf-8-sig"))
    coverage = artifact["meta"]["coverage"]

    actual_links = [link for rec in db["recommendations"] for link in rec.get("guideline_links") or []]
    actual_linked_diseases = {rec["id"] for rec in db["recommendations"] if rec.get("guideline_links")}
    actual_unmatched = {
        rec["id"] for rec in db["recommendations"] if not rec.get("guideline_links")
    }
    actual_guidelines = {link["guideline_id"] for link in actual_links}

    assert coverage["calculator_diseases"] == len(db["recommendations"])
    assert coverage["links"] == len(actual_links) == len(artifact["links"])
    assert coverage["linked_diseases"] == len(actual_linked_diseases)
    assert coverage["unmatched_diseases"] == len(actual_unmatched)
    assert coverage["linked_guidelines"] == len(actual_guidelines)

    by_method: dict[str, int] = {}
    for link in actual_links:
        by_method[link["method"]] = by_method.get(link["method"], 0) + 1
    # Артефакт декларирует все методы, включая нулевые (TITLE_EXACT: 0) —
    # отсутствующий в подсчёте метод означает ноль, а не расхождение.
    declared = coverage["links_by_method"]
    assert set(by_method) <= set(declared), (by_method, declared)
    for method, count in declared.items():
        assert by_method.get(method, 0) == count, f"{method}: {by_method.get(method, 0)} != {count}"
    assert coverage["linked_diseases"] + coverage["unmatched_diseases"] == coverage["calculator_diseases"]


# ── граница двух валидаторов ─────────────────────────────────────────────────

_BROWSER_CATS = ("нет cr_year", "нет cr_id", "нет duration_days", "нет route", "вне сценария age_group")

_BUILD_CATS = (
    ("age_group вне сценария", "outside scenario age_group"),
    ("нет режима для возраста", "no regimen for age_group"),
    ("нет duration_days", "missing duration_days"),
    ("нет route", "no route declared"),
    ("нет дозы", "no dose at all"),
    ("нет regimen_label", "no regimen_label"),
    ("duration_days не разобран", "unclassifiable free text"),
    ("маршрут вне расчётного контура", "cannot render it"),
    ("композитная таблетка", "tablets (by total"),
)


def _browser_validator_counts() -> dict[str, int]:
    """Запускает браузерный ``validateDB()`` из собранного HTML на реальной БД."""
    import subprocess
    import tempfile

    html = (ROOT / "antibiotic_calc.html").read_text(encoding="utf-8")
    script = next(
        body
        for _attrs, body in re.findall(r"<script(?P<a>[^>]*)>(?P<body>.*?)</script>", html, re.S)
        if "function validateDB(" in body
    )
    match = re.search(r"function validateDB\(", script)
    i, depth, started = match.start(), 0, False
    while i < len(script):
        if script[i] == "{":
            depth += 1
            started = True
        elif script[i] == "}":
            depth -= 1
            if started and depth == 0:
                i += 1
                break
        i += 1
    fn = script[match.start():i]
    db = json.loads(
        re.search(r'<script id="db-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    )
    path = Path(tempfile.mkdtemp()) / "v.js"
    path.write_text(
        f"const DB = {json.dumps(db, ensure_ascii=False)};\n{fn}\n"
        "const r = validateDB(); console.log(JSON.stringify(r));\n",
        encoding="utf-8",
    )
    out = subprocess.run([_node(), str(path)], capture_output=True, text=True, timeout=300, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def test_the_two_validators_share_exactly_the_expected_categories():
    """Шапка браузера и сборочный валидатор имеют РАЗНЫЙ объём — и это закреплено.

    Раньше расхождение было молчаливым: шапка показывала «⚠️ 124 пред», а сборка
    знала о 264, и расхождение по возрастной группе (60) браузер не видел вовсе.
    Теперь общее покрыто, а остаток разделён осознанно: браузерный валидатор
    показывает то, что видит пользователь собранным HTML, сборочный — полный
    гейт данных. Тест фиксирует обе границы, поэтому добавление проверки в один
    валидатор без другого упадёт, а не пройдёт незамеченным.
    """
    import collections
    import subprocess

    browser = _browser_validator_counts()
    b_counts = collections.Counter()
    for warn in browser["warns"]:
        for cat in _BROWSER_CATS:
            if cat in warn:
                b_counts[cat] += 1
                break
        else:
            raise AssertionError(f"браузерный валидатор выдал неучтённую категорию: {warn[:120]}")

    build_out = subprocess.run(
        [_node(), str(ROOT / "db" / "validate_db.js")],
        capture_output=True, text=True, cwd=ROOT, timeout=300, check=True,
    ).stdout
    bu_counts = collections.Counter()
    for line in build_out.splitlines():
        if "WARN:" not in line:
            continue
        for cat, needle in _BUILD_CATS:
            if needle in line:
                bu_counts[cat] += 1
                break
        else:
            raise AssertionError(f"сборочный валидатор выдал неучтённую категорию: {line[:160]}")

    # Общее покрытие — ровно три категории, числа совпадают.
    shared = ("age_group вне сценария", "нет duration_days", "нет route")
    for cat in shared:
        browser_key = "вне сценария age_group" if "age_group" in cat else cat
        assert b_counts[browser_key] == bu_counts[cat], (cat, b_counts, bu_counts)
    assert b_counts["вне сценария age_group"] == 60
    assert b_counts["нет duration_days"] == 47
    assert b_counts["нет route"] == 29

    # Только браузер: cr_year сборочный валидатор не проверяет вовсе.
    assert b_counts["нет cr_year"] == 48
    assert "нет cr_id" not in b_counts or b_counts["нет cr_id"] == 0

    # Только сборка: полный гейт данных.
    assert bu_counts["нет режима для возраста"] == 59
    assert bu_counts["нет дозы"] == 27
    assert bu_counts["нет regimen_label"] == 27
    assert bu_counts["duration_days не разобран"] == 12
    assert bu_counts["маршрут вне расчётного контура"] == 2
    assert bu_counts["композитная таблетка"] == 1

    assert sum(b_counts.values()) == len(browser["warns"]) == 184
    assert sum(bu_counts.values()) == 264
    assert browser["errs"] == []
