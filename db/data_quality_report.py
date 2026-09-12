#!/usr/bin/env python
"""Turn every validate_db.js finding into a row a physician or owner can act on.

``node db/validate_db.js`` reports 264 findings across nine categories. A count per
category is not a worklist: it carries no location, no context, and no question. This tool
emits one row per finding, with the same predicates as the validator — so the totals must
match exactly, and a test enforces that.

Each row carries:
* where it is (nozology, scenario, line, drug, regimen index);
* the context needed to decide (the КР text, the available forms, both age groups, …);
* the single question the reviewer has to answer;
* whether it would become a hard ERROR once the nozology is unblocked.

The last point matters: the validator downgrades these to warnings only while
``calculation_blocked`` is true. Unblocking a nozology turns some of them into build
failures, and the owner should know which before signing, not after.

This tool never changes anything and never writes to ``db/``.

Usage:
    python db/data_quality_report.py                          # summary on stdout
    python db/data_quality_report.py --json generated/…json   # machine-readable worklist
    python db/data_quality_report.py --category NO_DOSE       # one category only
    python db/data_quality_report.py --strict                 # exit 1 on policy breach
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "antibio_db.json"
DEFAULT_REPORT = PROJECT_ROOT / "generated" / "data_quality_report.json"

# ── константы, дословно повторяющие db/validate_db.js ─────────────────────────
ROUTES = ("per_os", "iv", "im")
NON_CALCULABLE_ROUTES = ("topical",)
AGE_GROUPS = ("neonate", "child", "adult", "all")
NUMERIC = re.compile(r"^\d+(\.\d+)?$")
NUMERIC_RANGE = re.compile(r"^\d+(\.\d+)?\s*-\s*\d+(\.\d+)?$")
COMPOSITE = re.compile(r"^(\d+(?:\.\d+)?)\+(\d+(?:\.\d+)?)\s*мг")

AGE_LABEL = {
    "neonate": "новорождённые (0-28 д)",
    "child": "дети (1 мес - 17 лет)",
    "adult": "взрослые (>18 лет)",
    "all": "все возрастные группы",
}

# Чем выше, тем раньше строка окажется в очереди: риск для пациента важнее алфавита.
SEVERITY_ORDER = {
    "NO_DOSE": 0,
    "COMPOSITE_TABLET_BASIS": 1,
    "AGE_GROUP_MISMATCH": 2,
    "UNROUTABLE_ROUTE": 3,
    "NO_REGIMEN_FOR_AGE": 4,
    "NO_REGIMEN_LABEL": 5,
    "UNCLASSIFIABLE_DURATION": 6,
    "MISSING_DURATION": 7,
    "NO_ROUTE": 8,
}

CATEGORY_QUESTION = {
    "NO_DOSE": (
        "Режим без числовой дозы — калькулятор честно не считает по нему. "
        "Какую дозу назначить: укажите dose_mg_kg_day, dose_mg_day_fixed или single_dose_mg."
    ),
    "COMPOSITE_TABLET_BASIS": (
        "Доза выражена по СУММЕ компонентов композитной таблетки, а калькулятор делит на "
        "ПЕРВЫЙ компонент. Что верно: доза в мг или концентрация формы?"
    ),
    "AGE_GROUP_MISMATCH": (
        "Что неверно: age_group сценария или принадлежность режима этому сценарию? "
        "Калькулятор уже отказывается считать по такому сценарию."
    ),
    "UNROUTABLE_ROUTE": (
        "Маршрут объявлен, но калькулятор не умеет его рассчитывать. Нужен ли расчёт по "
        "этому препарату, и если да — по какому маршруту?"
    ),
    "NO_REGIMEN_FOR_AGE": (
        "Препарат предлагается в сценарии, доступном для этого возраста, но режима на него "
        "нет. Добавить режим или исключить возраст из сценария?"
    ),
    "NO_REGIMEN_LABEL": (
        "Без regimen_label режим нельзя закрепить в calculator_binding (личный режим врача). "
        "Как назвать этот режим?"
    ),
    "UNCLASSIFIABLE_DURATION": (
        "Длительность курса задана свободным текстом, который не разбирается машиной. "
        "Сколько дней, или это действительно не фиксированный срок?"
    ),
    "MISSING_DURATION": (
        "Длительность курса не указана. Сколько дней, или срок зависит от клинической "
        "динамики?"
    ),
    "NO_ROUTE": (
        "У препарата не объявлен маршрут введения — калькулятор не может выбрать форму. "
        "Какой маршрут?"
    ),
}

DIRECTION_HINT = {
    ("child", "adult"): "Сценарий объявлен взрослым, но режим детский — проверьте, нужна ли там детская доза.",
    ("adult", "child"): "Сценарий объявлен детским, но режим взрослый. Взрослая доза в детском сценарии наиболее опасна.",
    ("adult", "neonate"): "Сценарий объявлен неонатальным, но режим взрослый. Взрослая доза у новорождённого наиболее опасна.",
    ("neonate", "adult"): "Сценарий объявлен взрослым, но режим неонатальный — проверьте принадлежность режима.",
    ("neonate", "child"): "Сценарий объявлен детским, но режим неонатальный — проверьте, нужно ли делить сценарии.",
    ("child", "neonate"): "Сценарий объявлен неонатальным, но режим детский — проверьте принадлежность режима.",
}


def _identity(drug: dict[str, Any]) -> str:
    if drug.get("drug_ref"):
        return str(drug["drug_ref"])
    return "+".join(drug.get("combo_ref") or []) or "?"


def _forms_of(db: dict[str, Any], drug_ref: str | None) -> list[str]:
    if not drug_ref:
        return []
    entry = (db.get("drugs_reference") or {}).get(drug_ref) or {}
    return [
        f"{form.get('form_type', '?')}: {form.get('concentration', '—')}"
        for form in entry.get("forms") or []
    ]


def _dose_text(regimen: dict[str, Any]) -> str:
    unit = regimen.get("dose_unit") or "мг"
    parts = []
    if regimen.get("single_dose_mg") is not None:
        parts.append(f"{regimen['single_dose_mg']} {unit} разово")
    if regimen.get("dose_mg_day_fixed") is not None:
        parts.append(f"{regimen['dose_mg_day_fixed']} {unit}/сут фикс.")
    if regimen.get("dose_mg_kg_day") is not None:
        parts.append(f"{regimen['dose_mg_kg_day']} {unit}/кг/сут")
    if regimen.get("dose_range_mg_kg_day"):
        parts.append(f"диапазон {regimen['dose_range_mg_kg_day']} {unit}/кг/сут")
    return "; ".join(parts) if parts else "доза не указана"


def _kr_text(drug: dict[str, Any], regimen: dict[str, Any], limit: int = 240) -> str:
    """Текст КР рядом с режимом — по нему врач восстанавливает дозу или срок."""
    for source in (regimen.get("indication_note"), drug.get("indication_note"),
                   regimen.get("duration_note")):
        if isinstance(source, str) and source.strip():
            text = " ".join(source.split())
            return text[:limit] + ("…" if len(text) > limit else "")
    return ""


def build_report(db_path: Path = DB_PATH, only_category: str | None = None) -> dict[str, Any]:
    db = json.loads(Path(db_path).read_text(encoding="utf-8-sig"))
    rows: list[dict[str, Any]] = []

    def add(category, rec, scenario, line, drug, regimen_index, **extra):
        if only_category and category != only_category:
            return
        blocked = rec.get("calculation_blocked") is not False
        # Дискриминатор обязателен: у находок уровня препарата одна и та же
        # локализация встречается несколько раз (два возраста без режима, два
        # нерасчётных маршрута), и без него finding_id сталкивался — 264 находки
        # давали только 250 уникальных ключей.
        discriminator = (
            extra.get("missing_age_group")
            or extra.get("route_declared")
            or extra.get("form_concentration")
            or ""
        )
        rows.append(
            {
                "finding_id": (
                    f"dq_{category.lower()}_{rec.get('id')}_{scenario.get('id')}_"
                    f"L{line.get('line_number')}_{_identity(drug)}"
                    + (f"_r{regimen_index}" if regimen_index is not None else "")
                    + (f"_{discriminator}" if discriminator else "")
                ),
                "category": category,
                "question_for_reviewer": CATEGORY_QUESTION[category],
                "disease_id": rec.get("id"),
                "disease_name": rec.get("name"),
                "cr_id": rec.get("cr_id") or "—",
                "calculation_blocked": blocked,
                # Пока нозология заблокирована, валидатор пишет WARN; после разблокировки
                # часть категорий станет ERROR и уронит сборку.
                "becomes_error_when_unblocked": blocked and category in _ERROR_WHEN_OPEN,
                "scenario_id": scenario.get("id"),
                "scenario_name": scenario.get("name"),
                "scenario_age_group": scenario.get("age_group"),
                "line_number": line.get("line_number"),
                "drug": _identity(drug),
                "drug_ref": drug.get("drug_ref"),
                "combo_ref": drug.get("combo_ref"),
                "route": drug.get("route") or [],
                "regimen_index": regimen_index,
                **extra,
            }
        )

    for rec in db.get("recommendations") or []:
        for scenario in rec.get("scenarios") or []:
            sc_age = scenario.get("age_group")
            reachable = [a for a in AGE_GROUPS if a != "all"] if sc_age == "all" else [sc_age]
            for line in scenario.get("lines") or []:
                for drug in line.get("drugs") or []:
                    regimens = drug.get("regimens") or []

                    if not drug.get("route"):
                        add("NO_ROUTE", rec, scenario, line, drug, None,
                            available_forms=_forms_of(db, drug.get("drug_ref")))
                    else:
                        for route in drug["route"]:
                            if route in NON_CALCULABLE_ROUTES:
                                add("UNROUTABLE_ROUTE", rec, scenario, line, drug, None,
                                    route_declared=route,
                                    available_forms=_forms_of(db, drug.get("drug_ref")))

                    for age in reachable:
                        if not age or not regimens:
                            continue
                        eligible = [r for r in regimens if r.get("age_group") in (age, "all")]
                        if not eligible:
                            add("NO_REGIMEN_FOR_AGE", rec, scenario, line, drug, None,
                                missing_age_group=age,
                                missing_age_label=AGE_LABEL.get(age, age),
                                ages_with_regimens=sorted({r.get("age_group") for r in regimens}))

                    for ri, regimen in enumerate(regimens):
                        reg_age = regimen.get("age_group")

                        if (reg_age and sc_age and reg_age != "all" and sc_age != "all"
                                and reg_age != sc_age):
                            add("AGE_GROUP_MISMATCH", rec, scenario, line, drug, ri,
                                regimen_age_group=reg_age,
                                regimen_age_label=AGE_LABEL.get(reg_age, reg_age),
                                scenario_age_label=AGE_LABEL.get(sc_age, sc_age),
                                direction=f"режим {reg_age} в сценарии {sc_age}",
                                regimen_dose=_dose_text(regimen),
                                reviewer_hint=DIRECTION_HINT.get((reg_age, sc_age), ""))

                        if (regimen.get("dose_mg_kg_day") is None
                                and regimen.get("dose_mg_day_fixed") is None
                                and regimen.get("single_dose_mg") is None):
                            add("NO_DOSE", rec, scenario, line, drug, ri,
                                regimen_age_group=reg_age,
                                regimen_label=regimen.get("regimen_label") or "",
                                freq_per_day=regimen.get("freq_per_day"),
                                kr_text=_kr_text(drug, regimen))

                        label = regimen.get("regimen_label")
                        if not (isinstance(label, str) and label.strip()):
                            add("NO_REGIMEN_LABEL", rec, scenario, line, drug, ri,
                                regimen_age_group=reg_age,
                                regimen_dose=_dose_text(regimen),
                                freq_per_day=regimen.get("freq_per_day"))

                        raw = (regimen.get("duration_days").strip()
                               if isinstance(regimen.get("duration_days"), str)
                               else regimen.get("duration_days"))
                        if raw is None or raw == "":
                            add("MISSING_DURATION", rec, scenario, line, drug, ri,
                                regimen_age_group=reg_age,
                                duration_note=regimen.get("duration_note") or "",
                                duration_kind=(regimen.get("duration_parsed") or {}).get("kind"),
                                kr_text=_kr_text(drug, regimen, limit=160))
                        elif isinstance(regimen.get("duration_days"), str):
                            kind = (regimen.get("duration_parsed") or {}).get("kind")
                            if (not NUMERIC.match(str(raw)) and not NUMERIC_RANGE.match(str(raw))
                                    and (kind is None or kind == "NOT_FIXED")):
                                add("UNCLASSIFIABLE_DURATION", rec, scenario, line, drug, ri,
                                    regimen_age_group=reg_age,
                                    duration_text=str(raw),
                                    duration_kind=kind)

                        single = (regimen.get("single_dose_mg")
                                  if isinstance(regimen.get("single_dose_mg"), (int, float))
                                  else (regimen.get("dose_mg_day_fixed") / regimen["freq_per_day"]
                                        if isinstance(regimen.get("dose_mg_day_fixed"), (int, float))
                                        and regimen.get("freq_per_day") else None))
                        entry = ((db.get("drugs_reference") or {}).get(drug["drug_ref"])
                                 if drug.get("drug_ref") else None)
                        if single and single > 0 and "per_os" in (drug.get("route") or []) and entry:
                            for form in entry.get("forms") or []:
                                if form.get("form_type") not in ("tablet", "capsule"):
                                    continue
                                m = COMPOSITE.match(str(form.get("concentration") or ""))
                                if not m:
                                    continue
                                first = float(m.group(1))
                                total = first + float(m.group(2))
                                mult_total = abs(single / total - round(single / total)) < 1e-9
                                mult_first = abs(single / first - round(single / first)) < 1e-9
                                if mult_total and not mult_first:
                                    add("COMPOSITE_TABLET_BASIS", rec, scenario, line, drug, ri,
                                        regimen_age_group=reg_age,
                                        single_dose_mg=single,
                                        form_concentration=form.get("concentration"),
                                        total_basis_mg=total,
                                        first_component_mg=first,
                                        tablets_by_total=single / total,
                                        tablets_by_first_component=single / first)

    counts = Counter(row["category"] for row in rows)
    diseases = Counter(row["disease_id"] for row in rows)

    return {
        "meta": {
            "artifact_type": "CALCULATOR_DATA_QUALITY_REVIEW_QUEUE",
            "schema_version": "1.0.0",
            "detected_by": "data-quality-worklist-v1",
            "purpose": "PHYSICIAN_REVIEW_ONLY",
            "source_db": Path(db_path).name,
            "category_filter": only_category,
            "predicate_parity": "предикаты дословно повторяют db/validate_db.js; "
                                "сверка закреплена тестом",
            "warning": (
                "Очередь проверки качества данных калькулятора. Инструмент вычисляет "
                "только структурные признаки и НЕ решает клинический вопрос. Пока "
                "нозология заблокирована, все находки — предупреждения; поле "
                "becomes_error_when_unblocked показывает, что станет ошибкой сборки "
                "после разблокировки."
            ),
        },
        "totals": {
            "findings": len(rows),
            "categories": len(counts),
            "diseases_affected": len(diseases),
            "in_open_nozologies": sum(1 for r in rows if not r["calculation_blocked"]),
            "would_block_unblocking": sum(1 for r in rows if r["becomes_error_when_unblocked"]),
        },
        "category_counts": {
            k: counts[k] for k in sorted(counts, key=lambda c: (SEVERITY_ORDER.get(c, 99), c))
        },
        "disease_counts": dict(sorted(diseases.items(), key=lambda kv: (-kv[1], kv[0]))),
        "queue": sorted(
            rows,
            key=lambda row: (
                SEVERITY_ORDER.get(row["category"], 99),
                0 if row["becomes_error_when_unblocked"] else 1,
                row["disease_id"] or "",
                row["scenario_id"] or "",
                row["line_number"] if row["line_number"] is not None else 0,
                row["drug"],
                row["regimen_index"] if row["regimen_index"] is not None else -1,
            ),
        ),
    }


# Категории, которые валидатор считает ошибкой на разблокированной нозологии.
_ERROR_WHEN_OPEN = {
    "NO_DOSE",
    "COMPOSITE_TABLET_BASIS",
    "AGE_GROUP_MISMATCH",
    "NO_REGIMEN_FOR_AGE",
    "NO_REGIMEN_LABEL",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Turn validate_db.js findings into an actionable worklist"
    )
    parser.add_argument("--db", default=str(DB_PATH), type=Path)
    parser.add_argument("--json", default=None, type=Path, help="write the machine-readable worklist here")
    parser.add_argument("--category", default=None, choices=sorted(SEVERITY_ORDER), help="one category only")
    parser.add_argument("--strict", action="store_true", help="exit 1 when an open nozology carries a finding")
    args = parser.parse_args(argv)

    report = build_report(args.db, args.category)
    totals = report["totals"]

    title = "Качество данных калькулятора"
    if args.category:
        title += f" · {args.category}"
    print(f"=== {title} ===")
    print(
        f"Находок: {totals['findings']} · категорий: {totals['categories']} · "
        f"нозологий затронуто: {totals['diseases_affected']}"
    )
    print(f"В нозологиях с открытым расчётом: {totals['in_open_nozologies']}")
    print(f"Станет ошибкой сборки после разблокировки: {totals['would_block_unblocking']}")

    print("\nКатегории (по клиническому риску):")
    for category, count in report["category_counts"].items():
        marker = " ⚠ станет ERROR" if category in _ERROR_WHEN_OPEN else ""
        print(f"  {count:4d}  {category}{marker}")

    print("\nНозологии (первые 10):")
    for disease, count in list(report["disease_counts"].items())[:10]:
        print(f"  {count:4d}  {disease}")

    if report["queue"]:
        print("\nПервые три записи:")
        for row in report["queue"][:3]:
            where = f"{row['disease_id']}/{row['scenario_id']}/L{row['line_number']}/{row['drug']}"
            if row["regimen_index"] is not None:
                where += f"[{row['regimen_index']}]"
            print(f"  · [{row['category']}] {where}")
            print(f"    {row['question_for_reviewer']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"\nВорклист записан: {args.json}")

    if args.strict and totals["in_open_nozologies"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
