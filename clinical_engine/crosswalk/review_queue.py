"""Physician review queue for block-level crosswalk links.

``ICD10_BLOCK`` links match on a 3-character ICD-10 block rather than an exact
code, so they are plausible but unproven: «Воспалительные поражения
позвоночника» reaches `pid` through block ``A18`` because the calculator
nosology carries ``A18.2``. That may be exactly right or completely wrong, and
**only a physician can tell**.

This module never decides clinical relevance. It computes *structural* risk
signals — facts about the link that need no medical judgement — and orders the
queue so a reviewer meets the most suspicious links first:

* ``EXTERNAL_CAUSE_ONLY`` — the only reason the link exists is an ICD-10
  chapter-XX external-cause code (``Y83``), which describes a circumstance of
  care, not a disease.
* ``AGE_DIRECTION_CONFLICT`` — the guideline title states an age population the
  calculator nosology excludes («…у детей» against ``age_groups: [adult]``).
* ``BLOCK_ONLY_DISEASE`` — the nosology has no exact-code link at all, so every
  piece of evidence for it is block-level.
* ``COARSE_SHARED_BLOCK`` — one guideline reaches several nosologies through the
  same block, which means the block is too coarse to separate them.
* ``ROUTINE`` — none of the above; still needs a human, just not first.

Output is a report artifact plus records shaped for
``review_workbench.storage.ReviewStore.import_issue``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .builder import METHOD_ICD10_BLOCK, icd_block

__all__ = ["build_review_queue", "classify_link", "to_issue_records", "main"]

REPORT_SCHEMA_VERSION = "1.0.0"
DETECTED_BY = "crosswalk-block-triage-v1"
DEFAULT_OUTPUT = Path("clinical_engine/resources/calculator_crosswalk_review_queue.json")

EXTERNAL_CAUSE_ONLY = "EXTERNAL_CAUSE_ONLY"
AGE_DIRECTION_CONFLICT = "AGE_DIRECTION_CONFLICT"
BLOCK_ONLY_DISEASE = "BLOCK_ONLY_DISEASE"
COARSE_SHARED_BLOCK = "COARSE_SHARED_BLOCK"
ROUTINE = "ROUTINE"

# Order doubles as the ranking: first matching category sets the band, the rest
# stay visible as flags so nothing is hidden by a louder signal.
CATEGORY_ORDER = (
    EXTERNAL_CAUSE_ONLY,
    AGE_DIRECTION_CONFLICT,
    BLOCK_ONLY_DISEASE,
    COARSE_SHARED_BLOCK,
    ROUTINE,
)
CATEGORY_SEVERITY = {
    EXTERNAL_CAUSE_ONLY: "HIGH",
    AGE_DIRECTION_CONFLICT: "HIGH",
    BLOCK_ONLY_DISEASE: "MEDIUM",
    COARSE_SHARED_BLOCK: "MEDIUM",
    ROUTINE: "LOW",
}

_PEDIATRIC_TITLE = re.compile(r"у детей|детск\w*|педиатр\w*|неонатальн\w*|новорождённ\w*|новорожденн\w*", re.I)
_ADULT_TITLE = re.compile(r"у взрослых|взросл\w*", re.I)
_CHILDREN = frozenset({"child", "neonate"})


def _is_external_cause(code: str) -> bool:
    """ICD-10 chapter XX (V01–Y98) — circumstances, not diseases."""
    return code[:1].upper() in {"V", "W", "X", "Y"}


def _age_conflict(guideline_title: str, age_groups: Sequence[str]) -> str | None:
    """Return a reason when the title contradicts the nosology's population."""
    groups = {str(g).lower() for g in age_groups}
    if not groups or "all" in groups:
        return None
    if _PEDIATRIC_TITLE.search(guideline_title) and not (groups & _CHILDREN):
        return f"КР описывает детей, нозология ограничена {sorted(groups)}"
    if _ADULT_TITLE.search(guideline_title) and "adult" not in groups:
        return f"КР описывает взрослых, нозология ограничена {sorted(groups)}"
    return None


def classify_link(
    link: Mapping[str, Any],
    *,
    disease_age_groups: Sequence[str] = (),
    disease_has_exact_link: bool = True,
    guideline_disease_count: int = 1,
) -> dict[str, Any]:
    """Attach structural risk flags to one block-level link. Pure function."""
    matched = [str(code) for code in (link.get("matched_icd10") or ())]
    title = str(link.get("guideline_title") or "")

    flags: list[str] = []
    notes: dict[str, str] = {}

    if matched and all(_is_external_cause(code) for code in matched):
        flags.append(EXTERNAL_CAUSE_ONLY)
        notes[EXTERNAL_CAUSE_ONLY] = (
            "единственное совпадение — код внешних причин МКБ-10 "
            f"({', '.join(matched)}), а не код заболевания"
        )

    age_reason = _age_conflict(title, disease_age_groups)
    if age_reason:
        flags.append(AGE_DIRECTION_CONFLICT)
        notes[AGE_DIRECTION_CONFLICT] = age_reason

    if not disease_has_exact_link:
        flags.append(BLOCK_ONLY_DISEASE)
        notes[BLOCK_ONLY_DISEASE] = "у нозологии нет ни одной связи по точному коду"

    if guideline_disease_count > 1:
        flags.append(COARSE_SHARED_BLOCK)
        notes[COARSE_SHARED_BLOCK] = (
            f"эта КР блочно связана с {guideline_disease_count} нозологиями — блок их не различает"
        )

    category = next((flag for flag in CATEGORY_ORDER if flag in flags), ROUTINE)
    return {
        "category": category,
        "severity": CATEGORY_SEVERITY[category],
        "flags": flags,
        "flag_notes": notes,
    }


def build_review_queue(
    crosswalk: Mapping[str, Any],
    calculator_db: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Rank every block-level link for physician review. Never edits the artifact."""
    links = list(crosswalk.get("links") or ())
    age_groups: dict[str, list[str]] = {}
    for rec in calculator_db.get("recommendations") or ():
        if isinstance(rec, Mapping):
            age_groups[str(rec.get("id"))] = [str(g) for g in (rec.get("age_groups") or ())]

    diseases_with_exact = {
        str(link.get("disease_id"))
        for link in links
        if str(link.get("method") or "") != METHOD_ICD10_BLOCK
    }
    diseases_per_guideline: Counter[str] = Counter()
    for link in links:
        if str(link.get("method") or "") == METHOD_ICD10_BLOCK:
            diseases_per_guideline[str(link.get("guideline_id"))] += 1

    rows: list[dict[str, Any]] = []
    for link in links:
        if str(link.get("method") or "") != METHOD_ICD10_BLOCK:
            continue
        disease_id = str(link.get("disease_id") or "")
        guideline_id = str(link.get("guideline_id") or "")
        verdict = classify_link(
            link,
            disease_age_groups=age_groups.get(disease_id, ()),
            disease_has_exact_link=disease_id in diseases_with_exact,
            guideline_disease_count=diseases_per_guideline.get(guideline_id, 1),
        )
        rows.append(
            {
                "queue_id": f"xwblock_{disease_id}_{guideline_id}",
                "disease_id": disease_id,
                "disease_name": str(link.get("disease_name") or ""),
                "cr_id": str(link.get("cr_id") or ""),
                "disease_age_groups": age_groups.get(disease_id, []),
                "guideline_id": guideline_id,
                "guideline_title": str(link.get("guideline_title") or ""),
                "guideline_years": list(link.get("guideline_years") or ()),
                "matched_icd10": [str(code) for code in (link.get("matched_icd10") or ())],
                "matched_blocks": sorted({b for b in (icd_block(c) for c in (link.get("matched_icd10") or ())) if b}),
                "sample_diagnosis_names": list(link.get("diagnosis_names") or ())[:3],
                **verdict,
                "question_for_reviewer": (
                    "Клинически ли релевантна эта КР для данной нозологии? "
                    "Связь выведена по блоку МКБ-10 и не подтверждена точным кодом."
                ),
                "decision_hint": "ACCEPT / REJECT / NEEDS_INFO — решает врач; инструмент не решает.",
            }
        )

    # Deterministic order: severity band, then category rank, then stable ids.
    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    category_rank = {name: index for index, name in enumerate(CATEGORY_ORDER)}
    rows.sort(
        key=lambda row: (
            severity_rank.get(row["severity"], 3),
            category_rank.get(row["category"], len(CATEGORY_ORDER)),
            row["disease_id"],
            row["guideline_id"],
        )
    )

    return {
        "meta": {
            "artifact_type": "CALCULATOR_GUIDELINE_REVIEW_QUEUE",
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "detected_by": DETECTED_BY,
            "purpose": "PHYSICIAN_REVIEW_ONLY",
            "warning": (
                "Очередь врачебной проверки блочных связей. Инструмент вычисляет только "
                "структурные признаки и НЕ решает клиническую релевантность. Связь остаётся "
                "NAVIGATION_ONLY до и после проверки."
            ),
            "source_artifact_sha256": str(crosswalk.get("content_sha256") or ""),
            "scope": "links where method == ICD10_BLOCK",
        },
        "coverage": {
            "block_links": len(rows),
            "block_diseases": len({row["disease_id"] for row in rows}),
            "block_guidelines": len({row["guideline_id"] for row in rows}),
            "exact_or_title_links_excluded": len(links) - len(rows),
            "by_category": dict(
                sorted(Counter(row["category"] for row in rows).items(), key=lambda kv: category_rank.get(kv[0], 99))
            ),
            "by_severity": dict(sorted(Counter(row["severity"] for row in rows).items())),
        },
        "queue": rows,
    }


def to_issue_records(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Shape the queue for ``ReviewStore.import_issue`` (idempotent by queue_id)."""
    meta = report.get("meta") or {}
    timestamp = str(meta.get("generated_at") or "")
    records: list[dict[str, Any]] = []
    for row in report.get("queue") or ():
        records.append(
            {
                "issue_id": str(row["queue_id"]),
                "object_id": f"{row['disease_id']}::{row['guideline_id']}",
                "object_type": "CalculatorGuidelineLink",
                "source": str(row["guideline_id"]),
                "page_cell_provenance": {
                    "method": METHOD_ICD10_BLOCK,
                    "matched_icd10": row["matched_icd10"],
                    "matched_blocks": row["matched_blocks"],
                    "sample_diagnosis_names": row["sample_diagnosis_names"],
                },
                "category": str(row["category"]),
                "severity": str(row["severity"]),
                "clinical_impact": str(row["question_for_reviewer"]),
                "detected_by": str(meta.get("detected_by") or DETECTED_BY),
                "status": "PENDING",
                "reviewer": "",
                "resolution": "",
                "timestamp": timestamp,
                "payload": dict(row),
            }
        )
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the physician review queue for block-level links")
    parser.add_argument("--crosswalk", default="clinical_engine/resources/calculator_crosswalk.json", type=Path)
    parser.add_argument("--db", default="db/antibio_db.json", type=Path)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, type=Path)
    parser.add_argument("--write", action="store_true", help="write the report artifact")
    args = parser.parse_args(list(argv) if argv is not None else None)

    crosswalk = json.loads(args.crosswalk.read_text(encoding="utf-8-sig"))
    calculator_db = json.loads(args.db.read_text(encoding="utf-8-sig"))
    report = build_review_queue(crosswalk, calculator_db)

    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        report["written"] = str(args.output)

    print(json.dumps({k: report[k] for k in ("meta", "coverage")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
