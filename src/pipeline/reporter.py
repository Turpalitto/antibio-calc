"""reporter.py — финальный отчёт."""

from collections import Counter
from typing import Any


def generate_report(items: list[dict[str, Any]]) -> str:
    total = len(items)
    downloaded = sum(1 for i in items if i.get("pdf_path"))
    failed = sum(1 for i in items if not i.get("pdf_path"))
    with_abx = sum(1 for i in items if i.get("has_antibiotics"))
    without_abx = total - with_abx

    drug_counter: Counter = Counter()
    diagnosis_counter: Counter = Counter()
    mkb_counter: Counter = Counter()

    for item in items:
        if item.get("has_antibiotics"):
            name = item.get("Name", "")[:80]
            diagnosis_counter[name] += 1
            for drug in item.get("abx_drugs_found", []):
                drug_counter[drug] += 1
            for m in (item.get("Mkbs") or []):
                mkb_name = m.get("MkbName", "")[:60]
                if mkb_name:
                    mkb_counter[mkb_name] += 1

    lines = [
        "=" * 60,
        "ФИНАЛЬНЫЙ ОТЧЁТ",
        "=" * 60,
        "",
        f"  Всего рекомендаций:            {total}",
        f"  Успешно скачано:               {downloaded}",
        f"  Не скачано:                    {failed}",
        "",
        f"  Рекомендаций с антибиотиками:  {with_abx}",
        f"  Рекомендаций без антибиотиков: {without_abx}",
        "",
        f"  Процент охвата:                {with_abx / total * 100:.1f}%" if total else "  Процент охвата: N/A",
        "",
        "-" * 60,
        "ТОП-50 наиболее часто встречающихся антибиотиков:",
        "-" * 60,
        "",
    ]

    for drug, count in drug_counter.most_common(50):
        lines.append(f"  {count:4d}  {drug}")

    lines += [
        "",
        "-" * 60,
        "ТОП-20 диагнозов с антибиотиками:",
        "-" * 60,
        "",
    ]
    for diag, count in diagnosis_counter.most_common(20):
        lines.append(f"  {count:4d}  {diag}")

    lines += [
        "",
        "-" * 60,
        "ТОП-20 МКБ с антибиотиками:",
        "-" * 60,
        "",
    ]
    for mkb, count in mkb_counter.most_common(20):
        lines.append(f"  {count:4d}  {mkb}")

    level_counter: Counter = Counter()
    for item in items:
        level = item.get("abx_level", "?")
        level_counter[level] += 1

    lines += [
        "",
        "-" * 60,
        "A/B/C/D CLASSIFICATION:",
        "-" * 60,
        "",
    ]
    for level in ["A", "B", "C", "D"]:
        lines.append(f"  Level {level}: {level_counter.get(level, 0)}")

    regimen_count = 0
    try:
        import sqlite3
        from config import DB_PATH
        if DB_PATH.exists():
            db = sqlite3.connect(str(DB_PATH))
            cur = db.execute("SELECT COUNT(*) FROM antibiotic_regimens WHERE validated = 1")
            regimen_count = cur.fetchone()[0]
            db.close()
    except Exception:
        pass

    if regimen_count > 0:
        lines += [
            "",
            "-" * 60,
            "KNOWLEDGE BASE:",
            "-" * 60,
            "",
            f"  Validated regimens: {regimen_count}",
        ]

    report_text = "\n".join(lines)
    return report_text
