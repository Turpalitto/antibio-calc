"""Tests for db/age_group_report.py — the age-addressability worklist.

``db/validate_db.js`` warns about 60 regimens that sit in a scenario declared for another
age group, and the calculator header shows the same count. A count is not a worklist:
a physician cannot act on "60". These tests pin the report's invariants, including the
two that must never regress — the report must agree with the validator, and it must never
claim to decide which side of the mismatch is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from db.age_group_report import AGE_GROUPS, DIRECTION_HINT, build_report, main


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


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


def _scenario(age, regimens, sid="sc"):
    return {
        "id": sid,
        "name": "Сценарий",
        "age_group": age,
        "lines": [{"line_number": 1, "drugs": [{"drug_ref": "amoxicillin", "regimens": regimens}]}],
    }


def _regimen(age, **over):
    base = {"age_group": age, "freq_per_day": 3, "single_dose_mg": 500, "duration_days": 7}
    base.update(over)
    return base


@pytest.fixture()
def fixture(tmp_path: Path):
    db_path = _write(
        tmp_path / "antibio_db.json",
        {
            "recommendations": [
                _rec(
                    id="mixed",
                    name="Смешанная",
                    scenarios=[
                        _scenario("child", [_regimen("child"), _regimen("adult")], sid="child_sc"),
                        _scenario("adult", [_regimen("child")], sid="adult_sc"),
                        _scenario("all", [_regimen("neonate")], sid="all_sc"),
                        _scenario("neonate", [_regimen("adult")], sid="neo_sc"),
                    ],
                ),
                _rec(
                    id="open_demo",
                    name="Открытая",
                    calculation_blocked=False,
                    scenarios=[_scenario("child", [_regimen("adult")], sid="open_sc")],
                ),
                _rec(
                    id="bogus",
                    name="Недопустимый возраст",
                    scenarios=[_scenario("toddler", [_regimen("infant")], sid="bogus_sc")],
                ),
            ]
        },
    )
    return db_path


def test_mismatches_are_found_and_consistent_regimes_are_not(fixture):
    report = build_report(fixture)

    # child_sc: child OK, adult mismatch. adult_sc: child mismatch.
    # all_sc: сценарий 'all' — расхождения быть не может. neo_sc: adult mismatch.
    # open_demo: adult mismatch.
    # bogus: оба age_group недопустимы — учтены как нарушение политики, а не как
    # расхождение адресации (иначе одна запись считалась бы дважды).
    directions = report["direction_counts"]
    assert directions.get("режим adult в сценарии child") == 2
    assert directions.get("режим child в сценарии adult") == 1
    assert directions.get("режим adult в сценарии neonate") == 1
    # Направлений, которых в фикстуре нет, в отчёте быть не должно.
    assert directions.get("режим child в сценарии neonate") is None
    assert directions.get("режим neonate в сценарии all") is None
    assert not any("toddler" in d or "infant" in d for d in directions), directions


def test_a_scenario_declared_all_never_produces_a_mismatch(fixture):
    report = build_report(fixture)
    assert not [row for row in report["queue"] if row["scenario_age_group"] == "all"], (
        "сценарий age_group 'all' адресован всем возрастам — расхождения быть не может"
    )


def test_dangerous_directions_are_sorted_first(fixture):
    """Режим старше сценария идёт первым: там доза может быть выше адресной."""
    report = build_report(fixture)
    rank = {"neonate": 0, "child": 1, "adult": 2}
    older = [
        i
        for i, row in enumerate(report["queue"])
        if rank[row["regimen_age_group"]] > rank[row["scenario_age_group"]]
    ]
    younger = [
        i
        for i, row in enumerate(report["queue"])
        if rank[row["regimen_age_group"]] < rank[row["scenario_age_group"]]
    ]
    assert older and younger
    assert max(older) < min(younger), "опасное направление обязано стоять в начале очереди"
    assert report["totals"]["regimen_older_than_scenario"] == len(older)


def test_open_nozologies_are_counted_separately(fixture):
    report = build_report(fixture)
    assert report["totals"]["in_open_nozologies"] == 1
    open_rows = [row for row in report["queue"] if not row["calculation_blocked"]]
    assert [row["disease_id"] for row in open_rows] == ["open_demo"]


def test_unknown_age_group_is_a_policy_breach_and_strict_fails(fixture, tmp_path, capsys):
    report = build_report(fixture)
    assert report["totals"]["policy_breaches"] == 2
    codes = {breach["detail"].split(":")[0] for breach in report["policy_breaches"]}
    assert codes == {"UNKNOWN_SCENARIO_AGE_GROUP", "UNKNOWN_REGIMEN_AGE_GROUP"}

    out = tmp_path / "report.json"
    assert main(["--db", str(fixture), "--json", str(out), "--strict"]) == 1
    printed = capsys.readouterr().out
    assert "Нарушения fail-closed политики: 2" in printed
    assert out.exists()


def test_without_strict_the_exit_code_is_zero(fixture, tmp_path, capsys):
    assert main(["--db", str(fixture), "--json", str(tmp_path / "r.json")]) == 0
    assert "Все age_group" not in capsys.readouterr().out


def test_every_mismatch_carries_a_question_and_never_a_verdict(fixture):
    """Инструмент спрашивает, а не решает."""
    report = build_report(fixture)
    assert report["queue"], "в фикстуре должны быть расхождения"
    for row in report["queue"]:
        assert row["question_for_reviewer"], row
        assert "решает врач" in row["question_for_reviewer"]
        assert "reviewer_hint" in row
        # подсказка — гипотеза для проверяющего, не вердикт
        if row["reviewer_hint"]:
            assert "проверьте" in row["reviewer_hint"].lower() or "относится" in row["reviewer_hint"].lower()
    assert report["meta"]["purpose"] == "PHYSICIAN_REVIEW_ONLY"
    assert "НЕ решает" in report["meta"]["warning"]


def test_every_observed_direction_has_a_hint():
    """Для каждого встреченного направления есть подсказка, фолбэк пустой строкой."""
    rank_pairs = [
        (a, s)
        for a in AGE_GROUPS
        for s in AGE_GROUPS
        if a != "all" and s != "all" and a != s
    ]
    assert set(DIRECTION_HINT) == set(rank_pairs), (
        "набор подсказок обязан покрывать все шесть направлений"
    )


def test_queue_ids_are_unique(fixture):
    report = build_report(fixture)
    ids = [row["queue_id"] for row in report["queue"]]
    assert len(ids) == len(set(ids)), "queue_id обязан быть уникальным — по нему ведут учёт"


def test_report_over_the_real_database_matches_the_validator():
    """На реальной БД отчёт обязан найти ровно те же 60, что и validate_db.js."""
    import subprocess

    from db.age_group_report import DB_PATH

    node = __import__("shutil").which("node")
    if not node:
        pytest.skip("Node.js is unavailable")

    report = build_report(DB_PATH)
    assert report["totals"]["mismatches"] == 60
    assert report["totals"]["diseases_affected"] == 13
    assert report["totals"]["regimen_older_than_scenario"] == 19
    assert report["totals"]["in_open_nozologies"] == 0
    assert report["totals"]["policy_breaches"] == 0

    build = subprocess.run(
        [node, "db/validate_db.js"], capture_output=True, text=True, cwd=DB_PATH.parent.parent, timeout=300
    ).stdout
    validator = sum(1 for line in build.splitlines() if "WARN:" in line and "outside scenario age_group" in line)
    assert validator == report["totals"]["mismatches"], (validator, report["totals"])


def test_report_is_deterministic():
    first = build_report()
    second = build_report()
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(
        second, sort_keys=True, ensure_ascii=False
    )
