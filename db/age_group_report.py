#!/usr/bin/env python
"""Which regimens sit in a scenario meant for another age group?

``db/validate_db.js`` warns about 60 such regimens and the calculator header shows the
same count, but a number is not a worklist. This tool turns it into one: for every
mismatch it names the nozology, scenario, line, drug and regimen, states both age groups,
and asks the single question a physician has to answer.

The calculator already refuses to dose from a mismatched scenario (three independent
guards: the scenario card is not selectable, ``calculate()`` refuses, and the in-browser
``validateDB()`` reports it). So none of these regimens can produce a wrong dose today.
What is left is a data decision that only a physician can make: is the scenario's
``age_group`` wrong, or is the regimen in the wrong scenario?

This tool never changes anything and never writes to ``db/``.

Usage:
    python db/age_group_report.py                     # summary on stdout
    python db/age_group_report.py --json out.json     # machine-readable worklist
    python db/age_group_report.py --strict            # exit 1 on policy breach
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "antibio_db.json"
DEFAULT_REPORT = PROJECT_ROOT / "generated" / "age_group_report.json"

AGE_GROUPS = ("neonate", "child", "adult", "all")

AGE_LABEL = {
    "neonate": "новорождённые (0-28 д)",
    "child": "дети (1 мес - 17 лет)",
    "adult": "взрослые (>18 лет)",
    "all": "все возрастные группы",
}

# Which side of the mismatch is more likely to be the error, stated as a hypothesis for
# the reviewer — never as a verdict. The tool does not decide.
DIRECTION_HINT = {
    ("child", "adult"): (
        "Сценарий объявлен взрослым, но режим детский. Чаще всего это детская доза, "
        "перенесённая во взрослый сценарий, — проверьте, нужна ли она там."
    ),
    ("adult", "child"): (
        "Сценарий объявлен детским, но режим взрослый. Взрослая доза в детском сценарии "
        "наиболее опасна — проверьте в первую очередь."
    ),
    ("adult", "neonate"): (
        "Сценарий объявлен неонатальным, но режим взрослый. Взрослая доза у "
        "новорождённого — проверьте в первую очередь."
    ),
    ("neonate", "adult"): (
        "Сценарий объявлен взрослым, но режим неонатальный. Проверьте, относится ли "
        "режим к этому сценарию."
    ),
    ("neonate", "child"): (
        "Сценарий объявлен детским, но режим неонатальный. Проверьте, нужно ли "
        "разделять сценарии по возрасту."
    ),
    ("child", "neonate"): (
        "Сценарий объявлен неонатальным, но режим детский. Проверьте, относится ли "
        "режим к этому сценарию."
    ),
}

QUESTION = (
    "Что неверно: age_group сценария или принадлежность режима этому сценарию? "
    "Инструмент не решает — решает врач."
)


def _dose_of(regimen: dict[str, Any]) -> str:
    """Человекочитаемая доза режима, чтобы врач видел, о каком числе речь."""
    unit = regimen.get("dose_unit") or "мг"
    if regimen.get("single_dose_mg") is not None:
        return f"{regimen['single_dose_mg']} {unit} разово"
    if regimen.get("dose_mg_day_fixed") is not None:
        return f"{regimen['dose_mg_day_fixed']} {unit}/сут фикс."
    if regimen.get("dose_mg_kg_day") is not None:
        return f"{regimen['dose_mg_kg_day']} {unit}/кг/сут"
    return "доза не указана"


def build_report(db_path: Path = DB_PATH) -> dict[str, Any]:
    db = json.loads(Path(db_path).read_text(encoding="utf-8-sig"))

    rows: list[dict[str, Any]] = []
    unknown_age: list[dict[str, Any]] = []

    for rec in db.get("recommendations") or []:
        for si, scenario in enumerate(rec.get("scenarios") or []):
            sc_age = scenario.get("age_group")
            if sc_age is not None and sc_age not in AGE_GROUPS:
                unknown_age.append(
                    {
                        "code": "UNKNOWN_SCENARIO_AGE_GROUP",
                        "disease_id": rec.get("id"),
                        "scenario_id": scenario.get("id"),
                        "age_group": sc_age,
                    }
                )
            for li, line in enumerate(scenario.get("lines") or []):
                for di, drug in enumerate(line.get("drugs") or []):
                    for ri, regimen in enumerate(drug.get("regimens") or []):
                        reg_age = regimen.get("age_group")
                        if reg_age is not None and reg_age not in AGE_GROUPS:
                            unknown_age.append(
                                {
                                    "code": "UNKNOWN_REGIMEN_AGE_GROUP",
                                    "disease_id": rec.get("id"),
                                    "scenario_id": scenario.get("id"),
                                    "drug": drug.get("drug_ref") or drug.get("combo_ref"),
                                    "age_group": reg_age,
                                }
                            )
                        # Тот же предикат, что и в db/validate_db.js.
                        # Недопустимое значение age_group сюда не попадает: оно уже
                        # учтено как нарушение политики, а считать его ещё и
                        # «расхождением адресации» значит учесть одну запись дважды.
                        if reg_age not in AGE_GROUPS or sc_age not in AGE_GROUPS:
                            continue
                        if not (
                            reg_age
                            and sc_age
                            and reg_age != "all"
                            and sc_age != "all"
                            and reg_age != sc_age
                        ):
                            continue
                        rows.append(
                            {
                                "queue_id": (
                                    f"agegrp_{rec.get('id')}_{scenario.get('id')}_"
                                    f"{drug.get('drug_ref') or '_'.join(drug.get('combo_ref') or [])}_{ri}"
                                ),
                                "disease_id": rec.get("id"),
                                "disease_name": rec.get("name"),
                                "cr_id": rec.get("cr_id") or "—",
                                "calculation_blocked": rec.get("calculation_blocked") is not False,
                                "scenario_id": scenario.get("id"),
                                "scenario_name": scenario.get("name"),
                                "scenario_age_group": sc_age,
                                "scenario_age_label": AGE_LABEL.get(sc_age, sc_age),
                                "line_number": line.get("line_number"),
                                "line_index": li,
                                "drug_index": di,
                                "drug_ref": drug.get("drug_ref"),
                                "combo_ref": drug.get("combo_ref"),
                                "regimen_index": ri,
                                "regimen_age_group": reg_age,
                                "regimen_age_label": AGE_LABEL.get(reg_age, reg_age),
                                "regimen_label": regimen.get("regimen_label") or "",
                                "regimen_dose": _dose_of(regimen),
                                "freq_per_day": regimen.get("freq_per_day"),
                                "direction": f"режим {reg_age} в сценарии {sc_age}",
                                "reviewer_hint": DIRECTION_HINT.get((reg_age, sc_age), ""),
                                "question_for_reviewer": QUESTION,
                            }
                        )

    direction_counts = Counter(row["direction"] for row in rows)
    disease_counts = Counter(row["disease_id"] for row in rows)
    # Опасное направление — режим старше сценария: доза может быть выше адресной.
    RANK = {"neonate": 0, "child": 1, "adult": 2}
    higher = [
        row for row in rows if RANK.get(row["regimen_age_group"], -1) > RANK.get(row["scenario_age_group"], -1)
    ]

    breaches = [
        {
            "code": "UNKNOWN_AGE_GROUP",
            "disease_id": item["disease_id"],
            "detail": f"{item['code']}: {item['age_group']!r}",
        }
        for item in unknown_age
    ]

    return {
        "meta": {
            "artifact_type": "CALCULATOR_AGE_GROUP_REVIEW_QUEUE",
            "schema_version": "1.0.0",
            "detected_by": "age-group-consistency-v1",
            "purpose": "PHYSICIAN_REVIEW_ONLY",
            "scope": "regimens whose age_group differs from the enclosing scenario's age_group",
            "source_db": str(Path(db_path).name),
            "warning": (
                "Очередь врачебной проверки возрастной адресации. Инструмент вычисляет "
                "только структурное расхождение и НЕ решает, какая сторона неверна. "
                "Калькулятор уже отказывается считать по такому сценарию."
            ),
        },
        "totals": {
            "mismatches": len(rows),
            "diseases_affected": len(disease_counts),
            "regimen_older_than_scenario": len(higher),
            "in_open_nozologies": sum(1 for row in rows if not row["calculation_blocked"]),
            "policy_breaches": len(breaches),
        },
        "direction_counts": dict(sorted(direction_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "disease_counts": dict(sorted(disease_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "policy_breaches": breaches,
        # Опасные направления первыми: там режим адресован старшему возрасту, чем сценарий.
        "queue": sorted(
            rows,
            key=lambda row: (
                0 if RANK.get(row["regimen_age_group"], -1) > RANK.get(row["scenario_age_group"], -1) else 1,
                row["disease_id"] or "",
                row["scenario_id"] or "",
                row["line_number"] if row["line_number"] is not None else 0,
                row["regimen_index"],
            ),
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report regimens that sit in a scenario meant for another age group"
    )
    parser.add_argument("--db", default=str(DB_PATH), type=Path)
    parser.add_argument("--json", default=None, type=Path, help="write the machine-readable worklist here")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a fail-closed invariant is breached")
    args = parser.parse_args(argv)

    report = build_report(args.db)
    totals = report["totals"]

    print("=== Возрастная адресация сценариев ===")
    print(
        f"Расхождений: {totals['mismatches']} · нозологий затронуто: {totals['diseases_affected']} · "
        f"режим старше сценария: {totals['regimen_older_than_scenario']}"
    )
    print(f"В нозологиях с открытым расчётом: {totals['in_open_nozologies']}")

    print("\nНаправления:")
    for direction, count in report["direction_counts"].items():
        print(f"  {count:4d}  {direction}")

    print("\nНозологии (первые 10):")
    for disease, count in list(report["disease_counts"].items())[:10]:
        print(f"  {count:4d}  {disease}")

    if report["policy_breaches"]:
        print(f"\n❌ Нарушения fail-closed политики: {len(report['policy_breaches'])}")
        for breach in report["policy_breaches"][:20]:
            print(f"  {breach['code']}: {breach['disease_id']} — {breach['detail']}")
    else:
        print("\n✅ Все age_group из допустимого набора")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"\nВорклист записан: {args.json}")

    if args.strict and report["policy_breaches"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
