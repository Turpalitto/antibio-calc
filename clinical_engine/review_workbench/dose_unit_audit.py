"""Classify every unitless KB Dose without generating medical values."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Только для проверки типов: import_into_store принимает ReviewStore, но сам его
    # не использует в рантайме. Без объявления аннотация не разрешалась —
    # typing.get_type_hints падал с NameError.
    from clinical_engine.review_workbench.storage import ReviewStore

_SIMPLE_UNIT = re.compile(r"(?<![\w/])(мг|mg|г|g|мкг|mcg|µg|мл|ml|ед|ме|iu)(?![\w/])", re.I)
_COMPOUND_UNIT = re.compile(
    r"(?:мг|mg|г|g|мкг|mcg|µg|ед|ме|iu)\s*/\s*(?:кг|kg|мл|ml|л|l|сут\w*|день|day|час|h)", re.I
)
_CONCENTRATION = re.compile(r"%|(?:мг|mg|г|g|мкг|mcg)\s*/\s*(?:мл|ml|л|l)", re.I)
_NUMBER_ONLY = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*$")
_FREQUENCY_ROUTE = re.compile(r"раз|сут|день|внутр|перорал|в/в|в/м|oral|intraven|route", re.I)
_NARRATIVE = re.compile(r"доз|принимать|назнач|ввод|терап", re.I)


def classify(texts: list[str]) -> tuple[str, str | None, str]:
    text = " | ".join(dict.fromkeys(value.strip() for value in texts if value and value.strip()))
    if not text or len(text) < 2:
        return "H_INVALID_NOISE", None, "empty/trivial source wording"
    if _CONCENTRATION.search(text):
        return "D_CONCENTRATION_NOT_DOSE", None, "percentage/concentration syntax"
    compound = _COMPOUND_UNIT.search(text)
    if compound:
        return "I_UNSUPPORTED_COMPOUND_UNIT", compound.group(0), "exact compound unit in source"
    simple = _SIMPLE_UNIT.search(text)
    if simple:
        return "A_PARSER_MISSED_EXPLICIT_UNIT", simple.group(0), "exact simple unit in source"
    if _NUMBER_ONLY.fullmatch(text):
        return "G_GENUINELY_MISSING_UNIT", None, "numeric dose has no source unit"
    if not re.search(r"\d", text) and _FREQUENCY_ROUTE.search(text):
        return "E_MISCLASSIFIED_FREQUENCY_ROUTE", None, "route/frequency wording without dose"
    if not re.search(r"\d", text) and _NARRATIVE.search(text):
        return "F_NARRATIVE_DOSE_INSTRUCTION", None, "narrative instruction without numeric dose"
    return "J_REQUIRES_PHYSICIAN_REVIEW", None, "context insufficient for safe classification"


def audit(db_path: str | Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    object_rows = connection.execute("""
        SELECT id,content FROM objects WHERE type='Dose' AND (
            json_extract(content,'$.unit') IS NULL OR trim(coalesce(json_extract(content,'$.unit'),''))=''
        ) ORDER BY id
    """).fetchall()
    object_ids = {row["id"] for row in object_rows}
    provenance_rows = connection.execute("""
        SELECT obj_id,guideline_id,pdf,page,table_row,table_col,original_text
        FROM provenance ORDER BY obj_id,pdf,page,table_row,table_col
    """).fetchall()
    connection.close()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in provenance_rows:
        if row["obj_id"] in object_ids:
            grouped[row["obj_id"]].append(row)
    content_by_id = {row["id"]: row["content"] for row in object_rows}
    generated_at = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    for object_id, sources in grouped.items():
        content = json.loads(content_by_id[object_id])
        texts = [str(row["original_text"] or "") for row in sources]
        texts.append(str(content.get("raw") or ""))
        category, source_unit, rationale = classify(texts)
        records.append({
            "issue_id": f"doseunit_{object_id}",
            "object_id": object_id,
            "object_type": "Dose",
            "source": str(sources[0]["pdf"] or ""),
            "page_cell_provenance": [{
                "guideline_id": row["guideline_id"], "pdf": row["pdf"], "page": row["page"],
                "table_row": row["table_row"], "table_col": row["table_col"],
                "original_text": row["original_text"],
            } for row in sources],
            "category": category,
            "severity": "HIGH" if category in {
                "G_GENUINELY_MISSING_UNIT", "J_REQUIRES_PHYSICIAN_REVIEW"
            } else "MEDIUM",
            "clinical_impact": "Dose unit unavailable; object cannot support prescribing.",
            "detected_by": "p5.6-dose-unit-audit-v1",
            "status": "PENDING",
            "reviewer": "",
            "resolution": "",
            "timestamp": generated_at,
            "source_backed_unit": source_unit,
            "automatic_recovery_eligible": category == "A_PARSER_MISSED_EXPLICIT_UNIT",
            "rationale": rationale,
            "payload": content,
        })
    counts = Counter(record["category"] for record in records)
    return {
        "generated_at": generated_at,
        "total": len(records),
        "counts": dict(sorted(counts.items())),
        "automatically_recoverable": sum(record["automatic_recovery_eligible"] for record in records),
        "review_required": sum(record["category"] == "J_REQUIRES_PHYSICIAN_REVIEW" for record in records),
        "invalid_or_noise": sum(record["category"] in {
            "D_CONCENTRATION_NOT_DOSE", "E_MISCLASSIFIED_FREQUENCY_ROUTE", "H_INVALID_NOISE"
        } for record in records),
        "blocked": sum(record["category"] == "G_GENUINELY_MISSING_UNIT" for record in records),
        "records": records,
    }


def import_into_store(store: ReviewStore, result: dict[str, Any]) -> int:
    return sum(store.import_issue(record) for record in result["records"])
