"""Read-only, source-backed verification of normalized regimen fields.

This tool never approves or rejects clinical content. It compares stored fields
with exact source-page text and emits evidence for physician review.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Callable, Iterable
from contextlib import closing
from pathlib import Path
from typing import Any

from clinical_engine.corpus.locator import CorpusLocator

PageTextProvider = Callable[[str], list[str]]


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pdf_text(path: str) -> list[str]:
    import fitz  # Imported lazily: verifier unit tests need no extraction extra.

    with fitz.open(path) as document:
        return [page.get_text("text") for page in document]


def _resolve_pdf(locator: CorpusLocator, filename: str) -> Path | None:
    name = Path(filename).name
    for directory in locator.pdf_dirs():
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _page_text(pages: list[str], source_page: Any) -> str | None:
    try:
        index = int(str(source_page).strip()) - 1
    except (TypeError, ValueError):
        return None
    if index < 0 or index >= len(pages):
        return None
    return pages[index]


def _source_is_located(page_text: str, source_quote: str, drug: str) -> bool:
    page = _compact(page_text)
    quote = _compact(source_quote)
    drug_text = _compact(drug)
    if not page:
        return False
    if quote and quote in page:
        return True
    return bool(drug_text and drug_text in page)


def _comparison(stored: Any, guideline: Any, *, found: bool) -> dict[str, Any]:
    if not found:
        status = "UNVERIFIABLE"
    elif guideline is None:
        status = "UNVERIFIABLE"
    elif _compact(stored) == _compact(guideline):
        status = "MATCH"
    else:
        status = "MISMATCH"
    return {
        "status": status,
        "stored_value": None if stored is None else str(stored),
        "guideline_value": None if guideline is None else str(guideline),
    }


def _find_number_with_unit(text: str, units: Iterable[str]) -> str | None:
    unit_group = "|".join(re.escape(unit) for unit in units)
    match = re.search(rf"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:{unit_group})\b", text, re.I)
    return _number(match.group(1).replace(",", ".")) if match else None


def _compare_fields(regimen: dict[str, Any], page_text: str, located: bool) -> dict[str, dict[str, Any]]:
    page = _compact(page_text)
    drug = regimen.get("drug_normalized")
    drug_guideline = drug if _compact(drug) and _compact(drug) in page else None

    unit = _compact(regimen.get("dose_unit"))
    unit_aliases = {
        "mg": ("mg", "мг"),
        "g": ("g", "г"),
        "mcg": ("mcg", "мкг", "µg"),
        "мг": ("mg", "мг"),
        "г": ("g", "г"),
        "мкг": ("mcg", "мкг", "µg"),
    }.get(unit, (unit,) if unit else ())
    dose_guideline = _find_number_with_unit(page, unit_aliases) if unit_aliases else None

    route = _compact(regimen.get("route"))
    route_aliases = {
        "oral": ("oral", "per os", "внутрь", "перораль"),
        "po": ("po", "per os", "внутрь", "перораль"),
        "iv": ("iv", "в/в", "внутривенн"),
        "im": ("im", "в/м", "внутримыш"),
    }.get(route, (route,) if route else ())
    route_guideline = regimen.get("route") if any(alias in page for alias in route_aliases) else None

    frequency = _number(regimen.get("frequency"))
    frequency_match = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:раз\w*|times|x)\b", page, re.I)
    frequency_guideline = _number(frequency_match.group(1).replace(",", ".")) if frequency_match else None

    duration = _number(
        regimen.get("duration_recommended")
        if regimen.get("duration_recommended") is not None
        else regimen.get("duration_max")
    )
    duration_match = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:дн\w*|day\w*)\b", page, re.I)
    duration_guideline = _number(duration_match.group(1).replace(",", ".")) if duration_match else None

    return {
        "drug": _comparison(drug, drug_guideline, found=located),
        "dose": _comparison(_number(regimen.get("dose")), dose_guideline, found=located),
        "route": _comparison(regimen.get("route"), route_guideline, found=located),
        "frequency": _comparison(frequency, frequency_guideline, found=located),
        "duration": _comparison(duration, duration_guideline, found=located),
    }


def _load_regimen(locator: CorpusLocator, regimen_id: str) -> dict[str, Any] | None:
    with closing(locator.open_normalized_regimens()) as connection:
        connection.row_factory = __import__("sqlite3").Row
        row = connection.execute(
            "SELECT * FROM normalized_regimens WHERE regimen_id = ?", (regimen_id,)
        ).fetchone()
    return dict(row) if row else None


def verify_regimens(
    regimen_ids: Iterable[str],
    *,
    locator: CorpusLocator | None = None,
    page_text_provider: PageTextProvider | None = None,
    verify_pdf_hash: bool = True,
) -> list[dict[str, Any]]:
    """Verify regimens against exact source pages without changing source data."""

    locator = locator or CorpusLocator()
    provider = page_text_provider or _pdf_text
    reports: list[dict[str, Any]] = []
    for regimen_id in regimen_ids:
        regimen = _load_regimen(locator, str(regimen_id))
        if regimen is None:
            reports.append({
                "regimen_id": str(regimen_id),
                "recommendation_status": "UNVERIFIABLE",
                "quality_score": 0,
                "reason": "REGIMEN_NOT_FOUND",
                "field_comparisons": {},
            })
            continue

        pdf = _resolve_pdf(locator, str(regimen.get("source_pdf") or ""))
        page_text = ""
        hash_status = "NOT_CHECKED"
        if pdf is not None:
            pages = provider(str(pdf))
            page_text = _page_text(pages, regimen.get("source_page")) or ""
            if verify_pdf_hash:
                hashlib.sha256(pdf.read_bytes()).hexdigest()
                hash_status = "COMPUTED"

        located = bool(pdf) and _source_is_located(
            page_text, str(regimen.get("source_quote") or ""), str(regimen.get("drug_normalized") or "")
        )
        comparisons = _compare_fields(regimen, page_text, located)
        statuses = [item["status"] for item in comparisons.values()]
        if not located or all(status == "UNVERIFIABLE" for status in statuses):
            recommendation_status = "UNVERIFIABLE"
        elif "MISMATCH" in statuses:
            recommendation_status = "LIKELY_MISMATCH"
        elif all(status == "MATCH" for status in statuses):
            recommendation_status = "LIKELY_MATCH"
        else:
            recommendation_status = "UNVERIFIABLE"
        quality_score = round(100 * statuses.count("MATCH") / len(statuses)) if statuses else 0
        reports.append({
            "regimen_id": str(regimen_id),
            "guideline_id": regimen.get("guideline_id"),
            "source_pdf": regimen.get("source_pdf"),
            "source_page": regimen.get("source_page"),
            "pdf_path": str(pdf) if pdf else None,
            "pdf_hash_status": hash_status,
            "recommendation_status": recommendation_status,
            "quality_score": quality_score,
            "field_comparisons": comparisons,
        })
    return reports


def _ids_from_csv(path: str | Path) -> list[str]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        return [row["regimen_id"].strip() for row in csv.DictReader(stream) if row.get("regimen_id", "").strip()]


def _write_markdown(path: str | Path, reports: list[dict[str, Any]]) -> None:
    lines = ["# Clinical Guideline Verification", "", "## Field-by-field comparison", ""]
    for report in reports:
        lines.extend([
            f"### {report['regimen_id']}",
            f"- Status: **{report['recommendation_status']}**",
            f"- Quality score: {report['quality_score']}",
            f"- Source: `{report.get('source_pdf')}` page `{report.get('source_page')}`",
            "",
        ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: str | Path, reports: list[dict[str, Any]]) -> None:
    fields = ("regimen_id", "guideline_id", "source_pdf", "source_page", "recommendation_status", "quality_score")
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: report.get(key) for key in fields} for report in reports)


def build(
    *,
    regimen_ids: Iterable[str],
    from_workbench_csv: str | None = None,
    out_json: str,
    out_md: str,
    out_csv: str,
    locator: CorpusLocator | None = None,
    page_text_provider: PageTextProvider | None = None,
    verify_pdf_hash: bool = True,
) -> dict[str, Any]:
    ids = list(regimen_ids)
    if from_workbench_csv:
        ids.extend(_ids_from_csv(from_workbench_csv))
    ids = list(dict.fromkeys(str(item) for item in ids))
    reports = verify_regimens(
        ids,
        locator=locator,
        page_text_provider=page_text_provider,
        verify_pdf_hash=verify_pdf_hash,
    )
    Path(out_json).write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(out_md, reports)
    _write_csv(out_csv, reports)
    return {
        "total": len(reports),
        "likely_match": sum(item["recommendation_status"] == "LIKELY_MATCH" for item in reports),
        "likely_mismatch": sum(item["recommendation_status"] == "LIKELY_MISMATCH" for item in reports),
        "unverifiable": sum(item["recommendation_status"] == "UNVERIFIABLE" for item in reports),
    }
