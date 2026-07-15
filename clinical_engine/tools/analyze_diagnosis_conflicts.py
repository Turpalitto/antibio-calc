"""Analyze conflicting mappings in the AUTO_GENERATED_DRAFT diagnosis_index.

A "conflict" = one diagnosis_name string routing to MORE THAN ONE distinct
guideline_id. This tool classifies every such conflict by OBSERVABLE DATA
ONLY (ICD-10 set equality, guideline-title equality). It performs:

  - NO auto-merging
  - NO heuristics / fuzzy matching / synonym or spelling inference
  - NO clinical judgement / assumptions about which guideline is "correct"

Everything that cannot be decided from the raw stored data is left to the
doctor. Synonym / spelling / wording conflicts (near-duplicate DIFFERENT
diagnosis strings) are deliberately NOT detected here — that requires fuzzy
matching (a heuristic), which is out of scope. Only exact-string ->
multiple-guideline conflicts are covered. A supplementary, DETERMINISTIC
(case/whitespace-only) near-duplicate check is included separately.

Severity buckets (purely data-driven):
  CRITICAL — same diagnosis, ICD-10 sets DIFFER across guidelines.
  MEDIUM   — same diagnosis, ICD-10 IDENTICAL, guideline titles DIFFER.
  SAFE     — same diagnosis, ICD-10 IDENTICAL, titles IDENTICAL
             (only guideline_id differs -> likely duplicate ingestion).

Usage (from repo root):
    python -m clinical_engine.tools.analyze_diagnosis_conflicts \
        [--index clinical_engine/resources/diagnosis_index.json] \
        [--md diagnosis_index_review.md] \
        [--json diagnosis_index_review.json]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_INDEX = "clinical_engine/resources/diagnosis_index.json"
_DEFAULT_MD = "diagnosis_index_review.md"
_DEFAULT_JSON = "diagnosis_index_review.json"


def _load_entries(index_path: str) -> list[dict]:
    data = json.loads(Path(index_path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("entries", [])
    return data


def _classify(diagnosis: str, entries: list[dict]) -> dict:
    by_g: dict[str, dict] = defaultdict(lambda: {"icd": set(), "titles": set()})
    for e in entries:
        by_g[e["guideline_id"]]["icd"].update(e.get("icd10_codes") or [])
        title = (e.get("guideline_title") or "").strip()
        if title:
            by_g[e["guideline_id"]]["titles"].add(title)

    guidelines = []
    for gid in sorted(by_g):
        guidelines.append(
            {
                "guideline_id": gid,
                "icd10": sorted(by_g[gid]["icd"]),
                "titles": sorted(by_g[gid]["titles"]),
            }
        )

    icd_sets = {frozenset(g["icd10"]) for g in guidelines}
    all_titles = {t for g in guidelines for t in g["titles"]}
    icd_identical = len(icd_sets) == 1
    titles_identical = len(all_titles) <= 1

    if not icd_identical:
        severity = "CRITICAL"
        ctype = "DIFFERENT_ICD"
        reason = (
            "Одна и та же строка диагноза маршрутизируется на КР с РАЗНЫМИ "
            "наборами кодов ICD-10. Это либо клинически разные состояния под "
            "одной меткой, либо разное кодирование одного состояния — из "
            "сырых данных однозначно не определяется."
        )
        recommendation = (
            "ОБЯЗАТЕЛЬНАЯ врачебная проверка. Определить соответствие "
            "guideline ↔ клинический случай; при необходимости уточнить/"
            "разделить строку диагноза. Автоматически НЕ разрешается."
        )
        review = "да (обязательно)"
    elif not titles_identical:
        severity = "MEDIUM"
        ctype = "SAME_ICD_DIFFERENT_GUIDELINE"
        reason = (
            "Одинаковый набор ICD-10, но разные КР (разные заголовки). Одно и "
            "то же (по коду) состояние покрыто несколькими клиническими "
            "рекомендациями."
        )
        recommendation = (
            "Врач выбирает primary guideline (или подтверждает, что КР "
            "комплементарны). Автоматически НЕ разрешается."
        )
        review = "да (обязательно)"
    else:
        severity = "SAFE"
        ctype = "LIKELY_DUPLICATE"
        reason = (
            "ICD-10 и заголовок КР идентичны, различается только guideline_id "
            "— вероятный дубликат одной КР под разными идентификаторами."
        )
        recommendation = (
            "Техническая проверка куратора: подтвердить дубликат и оставить "
            "один guideline_id. Низкий клинический риск, но НЕ объединять "
            "автоматически."
        )
        review = "да (техническая проверка дубликата)"

    return {
        "diagnosis": diagnosis,
        "num_guidelines": len(guidelines),
        "guidelines": guidelines,
        "severity": severity,
        "conflict_type": ctype,
        "reason": reason,
        "recommendation": recommendation,
        "requires_doctor_review": review,
        "source": "metadata.sqlite :: antibiotic_regimens (AUTO_GENERATED_DRAFT)",
    }


def _deterministic_near_dups(entries: list[dict]) -> list[dict]:
    """Diagnosis strings identical after case+whitespace normalization but
    stored with different exact text. DETERMINISTIC only — no fuzzy matching.
    """
    norm_to_variants: dict[str, set[str]] = defaultdict(set)
    for e in entries:
        raw = e["diagnosis_name"]
        if not raw:
            continue
        norm = re.sub(r"\s+", " ", raw.strip().lower())
        norm_to_variants[norm].add(raw)
    return [
        {"normalized": norm, "stored_variants": sorted(v)}
        for norm, v in norm_to_variants.items()
        if len(v) > 1
    ]


def analyze(index_path: str) -> dict:
    entries = _load_entries(index_path)
    by_dx: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_dx[e["diagnosis_name"]].append(e)

    conflicts = []
    for dx, es in by_dx.items():
        if len({e["guideline_id"] for e in es}) > 1 and dx:
            conflicts.append(_classify(dx, es))

    order = {"CRITICAL": 0, "MEDIUM": 1, "SAFE": 2}
    conflicts.sort(key=lambda c: (order[c["severity"]], -c["num_guidelines"], c["diagnosis"]))

    near_dups = _deterministic_near_dups(entries)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "index_path": index_path,
        "total_entries": len(entries),
        "total_conflicts": len(conflicts),
        "counts": {
            "CRITICAL": sum(1 for c in conflicts if c["severity"] == "CRITICAL"),
            "MEDIUM": sum(1 for c in conflicts if c["severity"] == "MEDIUM"),
            "SAFE": sum(1 for c in conflicts if c["severity"] == "SAFE"),
        },
        "conflicts": conflicts,
        "deterministic_near_duplicate_names": near_dups,
    }


def _g_cell(guidelines: list[dict]) -> str:
    parts = []
    for g in guidelines:
        icd = ", ".join(g["icd10"]) or "—(нет ICD-10)"
        parts.append(f"`{g['guideline_id']}` → [{icd}]")
    return "<br>".join(parts)


def _title_cell(guidelines: list[dict]) -> str:
    parts = []
    for g in guidelines:
        titles = " / ".join(g["titles"]) or "—"
        parts.append(f"`{g['guideline_id']}`: {titles}")
    return "<br>".join(parts)


def _table(conflicts: list[dict], severity: str) -> str:
    rows = [c for c in conflicts if c["severity"] == severity]
    if not rows:
        return "_(нет записей)_\n"
    out = [
        "| # | Диагноз | guideline_id → ICD-10 | Заголовки КР (источник) | Причина | Рекомендация | Врач. проверка |",
        "|---:|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(rows, 1):
        dx = c["diagnosis"].replace("|", "\\|")
        out.append(
            f"| {i} | {dx} | {_g_cell(c['guidelines'])} | "
            f"{_title_cell(c['guidelines']).replace('|', chr(92) + '|')} | "
            f"{c['reason']} | {c['recommendation']} | {c['requires_doctor_review']} |"
        )
    return "\n".join(out) + "\n"


def render_md(a: dict) -> str:
    c = a["counts"]
    nd = a["deterministic_near_duplicate_names"]
    nd_block = "_(не обнаружено)_\n"
    if nd:
        lines = ["| Нормализованная форма | Хранимые варианты |", "|---|---|"]
        for x in nd:
            variants = " ⟂ ".join(f"`{v}`" for v in x["stored_variants"])
            lines.append(f"| {x['normalized']} | {variants} |")
        nd_block = "\n".join(lines) + "\n"

    return f"""# diagnosis_index — Conflict Review (для врачебной валидации)

> Источник: `{a['index_path']}` (AUTO_GENERATED_DRAFT) · сгенерировано {a['generated_at']}
> **Ничего не объединено автоматически. Без эвристик. Без клинических допущений.**
> Классификация — только по наблюдаемым данным (равенство множеств ICD-10 и заголовков КР).

## Сводка
- Всего записей в индексе: **{a['total_entries']}**
- Всего конфликтов (диагноз → >1 guideline_id): **{a['total_conflicts']}**
- 🔴 Критические (ICD-10 различаются): **{c['CRITICAL']}**
- 🟡 Средние (ICD-10 совпадают, КР разные): **{c['MEDIUM']}**
- 🟢 Безопасные (ICD-10 + заголовок идентичны — вероятный дубликат): **{c['SAFE']}**

## Методология (что сделано и что НЕ сделано)
- **Конфликт** = одна и та же строка диагноза сопоставлена нескольким разным `guideline_id`.
- Классификация исключительно по фактам: (1) равны ли множества ICD-10 у разных guideline; (2) равны ли заголовки КР.
- **НЕ выполнялось:** авто-объединение, нечёткое сравнение строк, определение синонимов, исправление орфографии, выбор «правильного» guideline, любые клинические допущения.
- **Синонимы / орфография / разные формулировки** (близкие, но РАЗНЫЕ строки диагнозов) здесь НЕ анализируются — их выявление требует нечёткого сопоставления (эвристика, вне scope). Оставлено врачу. Ниже приведена лишь ДЕТЕРМИНИСТИЧЕСКАЯ проверка (различия только в регистре/пробелах).
- Все конфликты, которые нельзя разрешить из сырых данных, помечены как требующие врачебной проверки.

## 🔴 Критические конфликты (ICD-10 различаются) — {c['CRITICAL']}
Разные наборы ICD-10 под одной строкой диагноза. Маршрутизация клинически неоднозначна. Обязательная врачебная проверка.

{_table(a['conflicts'], 'CRITICAL')}

## 🟡 Средние конфликты (ICD-10 совпадают, разные КР) — {c['MEDIUM']}
Одно (по коду) состояние покрыто несколькими КР. Врач выбирает primary.

{_table(a['conflicts'], 'MEDIUM')}

## 🟢 Безопасные конфликты (вероятные дубликаты) — {c['SAFE']}
ICD-10 и заголовок КР идентичны; различается только `guideline_id`. Низкий клинический риск, техническая проверка дубликата.

{_table(a['conflicts'], 'SAFE')}

## Дополнительно: детерминистические near-duplicate имена (только регистр/пробелы, БЕЗ нечёткого сопоставления)
Строки диагнозов, идентичные после нормализации регистра и пробелов, но хранимые по-разному. НЕ синонимы и НЕ опечатки — только форматирование. Синонимы/опечатки оставлены врачу.

{nd_block}
---
_Отчёт только для чтения. Никаких изменений в `diagnosis_index.json` не вносилось. Разрешение конфликтов — за врачом._
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=_DEFAULT_INDEX)
    ap.add_argument("--md", default=_DEFAULT_MD)
    ap.add_argument("--json", default=_DEFAULT_JSON)
    args = ap.parse_args()

    a = analyze(args.index)
    Path(args.md).write_text(render_md(a), encoding="utf-8")
    Path(args.json).write_text(json.dumps(a, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== diagnosis_index conflict review ===")
    print(f"total entries:   {a['total_entries']}")
    print(f"total conflicts: {a['total_conflicts']}")
    print(f"  CRITICAL: {a['counts']['CRITICAL']}")
    print(f"  MEDIUM:   {a['counts']['MEDIUM']}")
    print(f"  SAFE:     {a['counts']['SAFE']}")
    print(f"deterministic near-dup names: {len(a['deterministic_near_duplicate_names'])}")
    print(f"written: {args.md} , {args.json}")


if __name__ == "__main__":
    main()
