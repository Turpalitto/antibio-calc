"""Tests for db/data_quality_report.py — the actionable worklist behind validate_db.js.

``node db/validate_db.js`` reports 264 findings in nine categories. A count is not a
worklist. This tool emits one row per finding using the *same predicates*, so the totals
must match the validator exactly, category by category — that parity is the load-bearing
assertion here, because a worklist that silently drifts from the validator is worse than
no worklist.

It also records which findings would become build ERRORS once a nozology is unblocked:
the validator downgrades them to warnings only while ``calculation_blocked`` is true, so
the owner should know before signing, not after.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from db.data_quality_report import (
    AGE_GROUPS,
    CATEGORY_QUESTION,
    DIRECTION_HINT,
    SEVERITY_ORDER,
    build_report,
    main,
)

ROOT = Path(__file__).resolve().parents[2]
REAL_DB = ROOT / "db" / "antibio_db.json"


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _db(recs, drugs=None):
    return {
        "recommendations": recs,
        "drugs_reference": drugs or {"_note": "n", "amoxicillin": {"inn": "Амоксициллин", "forms": []}},
    }


def _rec(**over):
    base = {
        "id": "demo",
        "name": "Демонозология",
        "cr_id": "9_3",
        "calculation_blocked": True,
        "scenarios": [],
    }
    base.update(over)
    return base


def _scenario(age, drugs, sid="sc"):
    return {"id": sid, "name": "Сценарий", "age_group": age,
            "lines": [{"line_number": 1, "drugs": drugs}]}


def _drug(regimens, route=("per_os",), ref="amoxicillin"):
    return {"drug_ref": ref, "route": list(route), "regimens": regimens}


def _regimen(age, **over):
    base = {"age_group": age, "freq_per_day": 3, "single_dose_mg": 500,
            "duration_days": 7, "regimen_label": f"метка-{age}"}
    base.update(over)
    return base


# ── сверка с валидатором: главная проверка ───────────────────────────────────

_NEEDLES = {
    "AGE_GROUP_MISMATCH": "outside scenario age_group",
    "NO_REGIMEN_FOR_AGE": "no regimen for age_group",
    "MISSING_DURATION": "missing duration_days",
    "NO_ROUTE": "no route declared",
    "NO_DOSE": "no dose at all",
    "NO_REGIMEN_LABEL": "no regimen_label",
    "UNCLASSIFIABLE_DURATION": "unclassifiable free text",
    "UNROUTABLE_ROUTE": "cannot render it",
    "COMPOSITE_TABLET_BASIS": "tablets (by total",
}


def test_every_category_matches_validate_db_js_exactly():
    """Ворклист и валидатор обязаны найти одно и то же — по каждой категории."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")

    report = build_report(REAL_DB)
    out = subprocess.run([node, "db/validate_db.js"], capture_output=True, text=True,
                         cwd=ROOT, timeout=300).stdout
    warns = [line for line in out.splitlines() if "WARN:" in line]

    counted = {}
    for line in warns:
        for category, needle in _NEEDLES.items():
            if needle in line:
                counted[category] = counted.get(category, 0) + 1
                break
        else:
            raise AssertionError(f"валидатор выдал неучтённую категорию: {line[:160]}")

    assert counted == report["category_counts"], (counted, report["category_counts"])
    assert report["totals"]["findings"] == len(warns) == 264
    assert report["totals"]["categories"] == 9
    assert report["totals"]["in_open_nozologies"] == 0


def test_category_filter_reproduces_the_focused_view():
    """--category даёт ровно подмножество, ничего не теряя."""
    full = build_report(REAL_DB)
    for category, count in full["category_counts"].items():
        focused = build_report(REAL_DB, only_category=category)
        assert focused["totals"]["findings"] == count, category
        assert {row["category"] for row in focused["queue"]} == {category}
    total = sum(
        build_report(REAL_DB, only_category=c)["totals"]["findings"]
        for c in full["category_counts"]
    )
    assert total == full["totals"]["findings"], "фильтр теряет или дублирует находки"


# ── поведение на фикстуре ────────────────────────────────────────────────────

def test_each_category_is_detected_on_a_minimal_fixture(tmp_path: Path):
    db = _write(tmp_path / "db.json", _db([
        _rec(id="gaps", scenarios=[
            # NO_ROUTE: препарата без маршрута
            _scenario("child", [{"drug_ref": "amoxicillin", "regimens": [_regimen("child")]}], sid="no_route"),
            # UNROUTABLE_ROUTE: topical
            _scenario("child", [_drug([_regimen("child")], route=("topical",))], sid="unroutable"),
            # NO_DOSE + NO_REGIMEN_LABEL + MISSING_DURATION одним режимом
            _scenario("child", [_drug([_regimen(
                "child", single_dose_mg=None, dose_mg_day_fixed=None, dose_mg_kg_day=None,
                regimen_label=None, duration_days=None,
            )])], sid="empty"),
            # UNCLASSIFIABLE_DURATION: свободный текст, который не разбирается
            _scenario("child", [_drug([_regimen(
                "child", duration_days="до нормализации температуры",
                duration_parsed={"kind": "NOT_FIXED"},
            )])], sid="freetext"),
            # AGE_GROUP_MISMATCH + NO_REGIMEN_FOR_AGE
            _scenario("child", [_drug([_regimen("adult")])], sid="mismatch"),
            # NO_REGIMEN_FOR_AGE: сценарий 'all', режима на неонатальный возраст нет
            _scenario("all", [_drug([_regimen("adult")])], sid="all_ages"),
        ]),
    ]))
    report = build_report(db)
    found = {row["category"] for row in report["queue"]}
    assert {
        "NO_ROUTE", "UNROUTABLE_ROUTE", "NO_DOSE", "NO_REGIMEN_LABEL",
        "MISSING_DURATION", "UNCLASSIFIABLE_DURATION", "AGE_GROUP_MISMATCH",
        "NO_REGIMEN_FOR_AGE",
    } <= found, found


def test_composite_tablet_basis_is_detected(tmp_path: Path):
    payload = _db(
        [_rec(id="cotrim", scenarios=[_scenario("adult", [_drug([_regimen("adult", single_dose_mg=480)])])])],
        drugs={"_note": "n", "cotrimoxazole": {
            "inn": "Ко-тримоксазол",
            "forms": [{"form_type": "tablet", "concentration": "400+80 мг"}],
        }},
    )
    payload["recommendations"][0]["scenarios"][0]["lines"][0]["drugs"][0]["drug_ref"] = "cotrimoxazole"
    report = build_report(_write(tmp_path / "db.json", payload))
    rows = [r for r in report["queue"] if r["category"] == "COMPOSITE_TABLET_BASIS"]
    assert len(rows) == 1, report["category_counts"]
    row = rows[0]
    assert row["total_basis_mg"] == 480
    assert row["first_component_mg"] == 400
    assert row["tablets_by_total"] == 1
    assert row["tablets_by_first_component"] == 1.2


def test_a_clean_record_produces_nothing(tmp_path: Path):
    db = _write(tmp_path / "db.json", _db([
        _rec(id="clean", scenarios=[
            _scenario("adult", [_drug([_regimen("adult")])]),
            _scenario("child", [_drug([_regimen("child")])]),
        ]),
    ]))
    report = build_report(db)
    assert report["totals"]["findings"] == 0, report["queue"]


def test_scenario_declared_all_never_mismatches_but_can_miss_an_age(tmp_path: Path):
    db = _write(tmp_path / "db.json", _db([
        _rec(id="allages", scenarios=[_scenario("all", [_drug([_regimen("adult")])])]),
    ]))
    report = build_report(db)
    cats = [row["category"] for row in report["queue"]]
    assert "AGE_GROUP_MISMATCH" not in cats, "сценарий 'all' адресован всем возрастам"
    assert cats.count("NO_REGIMEN_FOR_AGE") == 2, cats  # neonate и child


def test_findings_in_an_open_nozology_are_not_marked_as_pending(tmp_path: Path):
    db = _write(tmp_path / "db.json", _db([
        _rec(id="open", calculation_blocked=False,
             scenarios=[_scenario("child", [_drug([_regimen("adult")])])]),
    ]))
    report = build_report(db)
    assert report["totals"]["in_open_nozologies"] > 0
    for row in report["queue"]:
        assert row["calculation_blocked"] is False
        assert row["becomes_error_when_unblocked"] is False, row["finding_id"]


def test_blocked_findings_that_would_break_the_build_are_flagged(tmp_path: Path):
    """Пока нозология закрыта — WARN; после разблокировки часть станет ERROR."""
    db = _write(tmp_path / "db.json", _db([
        _rec(id="blocked", scenarios=[_scenario("child", [_drug([_regimen(
            "child", single_dose_mg=None, dose_mg_day_fixed=None, dose_mg_kg_day=None,
        )])])]),
        _rec(id="blocked2", scenarios=[_scenario("child", [{"drug_ref": "amoxicillin", "regimens": []}])]),
    ]))
    report = build_report(db)
    by_cat = {row["category"]: row["becomes_error_when_unblocked"] for row in report["queue"]}
    assert by_cat.get("NO_DOSE") is True
    # NO_ROUTE остаётся предупреждением и после разблокировки
    if "NO_ROUTE" in by_cat:
        assert by_cat["NO_ROUTE"] is False


def test_rows_are_ordered_by_clinical_risk(tmp_path: Path):
    db = _write(tmp_path / "db.json", _db([
        _rec(id="mixed", scenarios=[
            _scenario("child", [{"drug_ref": "amoxicillin", "regimens": [_regimen("child")]}], sid="a"),
            _scenario("child", [_drug([_regimen("adult")])], sid="b"),
        ]),
    ]))
    report = build_report(db)
    order = [SEVERITY_ORDER[row["category"]] for row in report["queue"]]
    assert order == sorted(order), "очередь обязана идти по клиническому риску"
    assert report["queue"][0]["category"] == "NO_DOSE" or report["queue"][0]["category"] == "AGE_GROUP_MISMATCH"


def test_every_row_carries_a_question_and_never_a_verdict(tmp_path: Path):
    db = _write(tmp_path / "db.json", _db([
        _rec(id="mixed", scenarios=[
            _scenario("child", [{"drug_ref": "amoxicillin", "regimens": [_regimen("child")]}], sid="a"),
            _scenario("child", [_drug([_regimen("adult")])], sid="b"),
        ]),
    ]))
    report = build_report(db)
    assert report["queue"]
    for row in report["queue"]:
        assert row["question_for_reviewer"], row["finding_id"]
        assert row["question_for_reviewer"] == CATEGORY_QUESTION[row["category"]]
        assert "?" in row["question_for_reviewer"], "формулировка обязана быть вопросом"
    assert report["meta"]["purpose"] == "PHYSICIAN_REVIEW_ONLY"
    assert "НЕ решает" in report["meta"]["warning"]


def test_every_category_has_a_question_and_a_severity_rank():
    assert set(CATEGORY_QUESTION) == set(SEVERITY_ORDER)
    assert set(CATEGORY_QUESTION) == set(_NEEDLES)
    assert len(set(SEVERITY_ORDER.values())) == len(SEVERITY_ORDER), "ранги не должны повторяться"


def test_every_age_direction_has_a_hint():
    pairs = {(a, s) for a in AGE_GROUPS for s in AGE_GROUPS if a != "all" and s != "all" and a != s}
    assert set(DIRECTION_HINT) == pairs


def test_finding_ids_are_unique(tmp_path: Path):
    report = build_report(REAL_DB)
    ids = [row["finding_id"] for row in report["queue"]]
    assert len(ids) == len(set(ids)), "finding_id обязан быть уникальным — по нему ведут учёт"


def test_cli_writes_json_and_filters_by_category(tmp_path: Path, capsys):
    out = tmp_path / "worklist.json"
    assert main(["--json", str(out), "--category", "NO_DOSE"]) == 0
    printed = capsys.readouterr().out
    assert "NO_DOSE" in printed
    document = json.loads(out.read_text(encoding="utf-8-sig"))
    assert document["meta"]["category_filter"] == "NO_DOSE"
    assert document["totals"]["findings"] == 27
    assert {row["category"] for row in document["queue"]} == {"NO_DOSE"}


def test_strict_fails_only_when_an_open_nozology_carries_a_finding(tmp_path: Path):
    blocked = _write(tmp_path / "blocked.json", _db([
        _rec(id="b", scenarios=[_scenario("child", [_drug([_regimen("adult")])])]),
    ]))
    assert main(["--db", str(blocked)]) == 0

    opened = _write(tmp_path / "open.json", _db([
        _rec(id="o", calculation_blocked=False,
             scenarios=[_scenario("child", [_drug([_regimen("adult")])])]),
    ]))
    assert main(["--db", str(opened), "--strict"]) == 1


def test_report_is_deterministic():
    first = json.dumps(build_report(REAL_DB), sort_keys=True, ensure_ascii=False)
    second = json.dumps(build_report(REAL_DB), sort_keys=True, ensure_ascii=False)
    assert first == second
