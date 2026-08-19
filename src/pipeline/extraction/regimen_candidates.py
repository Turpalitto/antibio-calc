"""Source-linked regimen candidates extracted from structured guideline tables.

The module deliberately produces *review candidates*, never approved clinical
content.  Each candidate retains the exact PDF hash, page, table row/columns,
cell bounding boxes and source wording.  Ambiguous rows fail closed.
"""

from __future__ import annotations

import hashlib
import json
import re
import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import fitz

from .layout import LayoutProcessor
from .base import Document


_FOOTNOTE = re.compile(r"\[fn:(\d+)\]")
_ATC = re.compile(r"(?:(?:АТХ|ATX)\s*:?\s*)(J\d{2}[A-Z]{2}\d{2})", re.IGNORECASE)
_MG_KG_DAY = re.compile(
    r"(?P<low>\d+(?:[.,]\d+)?)\s*(?:[-–—]\s*(?P<high>\d+(?:[.,]\d+)?))?"
    r"\s*мг\s*/\s*кг\s*/\s*сут(?:ки)?",
    re.IGNORECASE,
)
_MG_KG_DOSE = re.compile(
    r"(?P<low>\d+(?:[.,]\d+)?)\s*(?:[-–—]\s*(?P<high>\d+(?:[.,]\d+)?))?"
    r"\s*мг\s*/\s*кг(?!\s*/\s*сут)",
    re.IGNORECASE,
)
_FIXED_DOSE = re.compile(
    r"(?P<low>\d+(?:[.,]\d+)?)\s*(?:[-–—]\s*(?P<high>\d+(?:[.,]\d+)?))?\s*(?P<unit>мг|г)\b",
    re.IGNORECASE,
)
_FREQUENCY = re.compile(
    r"(?:в|на|по)\s*(?P<low>\d+)\s*(?:[-–—]\s*(?P<high>\d+))?\s*"
    r"(?:при[её]м|введени)",
    re.IGNORECASE,
)
_ATC_DRUGS = {
    "J01CA04": "Амоксициллин",
    "J01CR02": "Амоксициллин+[Клавулановая кислота]",
    "J01CR01": "Ампициллин+[Сульбактам]",
    "J01DD04": "Цефтриаксон",
    "J01DC02": "Цефуроксим",
    "J01DD08": "Цефиксим",
    "J01FA09": "Кларитромицин",
}


@dataclass(frozen=True)
class CandidateRowGroup:
    """Exact table-row span and semantic columns for one source regimen."""

    page: int
    table_index: int
    row_start: int
    row_end: int
    drug_col: int
    dose_col: int
    duration_col: int | None = None
    therapy_line: str = "unknown"
    blocking_reasons: tuple[str, ...] = ()
    atc: str = ""
    drug: str = ""
    duration: str = ""
    population_constraints: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class GuidelineCandidateSpec:
    guideline_id: str
    guideline_title: str
    approval_year: int
    source_url: str
    diagnosis: str
    icd10: tuple[str, ...]
    table_pages: tuple[int, ...]  # one-based PDF pages
    duration: str
    duration_page: int
    duration_wording: str
    rubricator_revision: str = ""
    expected_pdf_sha256: str = ""
    expected_candidates_sha256: str = ""
    row_groups: tuple[CandidateRowGroup, ...] = ()


def candidate_spec_from_mapping(raw: Mapping[str, Any]) -> GuidelineCandidateSpec:
    """Load the declarative source-spec contract with strict required fields."""
    required = {
        "guideline_id", "guideline_title", "approval_year", "source_url",
        "diagnosis", "icd10", "table_pages", "duration", "duration_page",
        "duration_wording",
    }
    missing = sorted(required.difference(raw))
    if missing:
        raise ValueError("candidate source spec missing: " + ", ".join(missing))
    row_groups = tuple(
        CandidateRowGroup(
            page=int(item["page"]),
            table_index=int(item.get("table_index", 0)),
            row_start=int(item["row_start"]),
            row_end=int(item["row_end"]),
            drug_col=int(item.get("drug_col", 0)),
            dose_col=int(item.get("dose_col", 2)),
            duration_col=(
                int(item["duration_col"])
                if item.get("duration_col") is not None else None
            ),
            therapy_line=str(item.get("therapy_line") or "unknown"),
            blocking_reasons=tuple(str(reason) for reason in (item.get("blocking_reasons") or [])),
            atc=str(item.get("atc") or ""),
            drug=str(item.get("drug") or ""),
            duration=str(item.get("duration") or ""),
            population_constraints=(
                dict(item["population_constraints"])
                if "population_constraints" in item else None
            ),
        )
        for item in (raw.get("row_groups") or [])
    )
    return GuidelineCandidateSpec(
        guideline_id=str(raw["guideline_id"]),
        guideline_title=str(raw["guideline_title"]),
        approval_year=int(raw["approval_year"]),
        source_url=str(raw["source_url"]),
        diagnosis=str(raw["diagnosis"]),
        icd10=tuple(str(item) for item in raw["icd10"]),
        table_pages=tuple(int(item) for item in raw["table_pages"]),
        duration=str(raw["duration"]),
        duration_page=int(raw["duration_page"]),
        duration_wording=str(raw["duration_wording"]),
        rubricator_revision=str(raw.get("rubricator_revision") or ""),
        expected_pdf_sha256=str(raw.get("expected_pdf_sha256") or ""),
        expected_candidates_sha256=str(raw.get("expected_candidates_sha256") or ""),
        row_groups=row_groups,
    )


def load_candidate_spec(path: str | Path) -> GuidelineCandidateSpec:
    return candidate_spec_from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def extract_regimen_candidates(
    pdf_path: str | Path,
    spec: GuidelineCandidateSpec,
) -> list[dict[str, Any]]:
    """Extract pediatric table regimens with exact cell provenance.

    Cross-page continuation rows are joined only when the structure provides an
    incomplete prior row.  Rows containing multiple weight strata remain
    ``REVIEW_REQUIRED`` and are never marked calculation-ready.
    """
    path = Path(pdf_path).resolve()
    pdf_sha256 = sha256_file(path)
    document = fitz.open(path)
    processor = LayoutProcessor.__new__(LayoutProcessor)
    rows: list[dict[str, Any]] = []
    for page_number in spec.table_pages:
        page_index = page_number - 1
        tables = processor._extract_tables_pymupdf_native(
            document[page_index], page_index, str(path)
        )
        for table_index, table in enumerate(tables):
            grid = _table_grid(table)
            for row_index in range(table.rows):
                rows.append({
                    "page": page_number,
                    "page_index": page_index,
                    "table_index": table_index,
                    "row": row_index,
                    "cells": grid[row_index],
                    "cell_provenance": [
                        _cell_provenance(cell) for cell in table.cells if cell.row == row_index
                    ],
                })
    document.close()

    logical_rows = (
        _rows_from_groups(rows, spec.row_groups)
        if spec.row_groups else _join_continuation_rows(rows)
    )
    section = "unknown"
    candidates: list[dict[str, Any]] = []
    for row in logical_rows:
        cells = row["cells"]
        drug_col = int(row.get("drug_col", 0))
        dose_col = int(row.get("dose_col", 2))
        duration_col = row.get("duration_col")
        drug_cell = _clean(cells[drug_col] if len(cells) > drug_col else "")
        child_cell = _clean(cells[dose_col] if len(cells) > dose_col else "")
        row_text = " | ".join(_clean(cell) for cell in cells if _clean(cell))
        low = row_text.lower()
        if "препараты выбора" in low:
            section = "first"
            continue
        if "альтернативные препараты" in low:
            section = "alternative"
            continue
        if low.startswith("при аллергии"):
            section = "alternative"
            continue
        if row.get("therapy_line"):
            section = str(row["therapy_line"])
        atc_match = _ATC.search(drug_cell)
        declared_atc = str(row.get("declared_atc") or "").upper()
        if (not atc_match and not declared_atc) or not child_cell:
            continue
        parse_child_cell = re.sub(r"\[сноска \d+\]", "", child_cell)
        clauses = list(_MG_KG_DAY.finditer(parse_child_cell))
        basis = "MG_KG_PER_DAY"
        unit = "mg/kg/day"
        if not clauses:
            clauses = list(_MG_KG_DOSE.finditer(parse_child_cell))
            basis = "MG_KG_PER_DOSE"
            unit = "mg/kg/dose"
        if not clauses:
            clauses = list(_FIXED_DOSE.finditer(parse_child_cell))
            basis = "FIXED_PER_DOSE"
            unit = "mg/dose"
        if not clauses:
            continue

        atc = declared_atc or atc_match.group(1).upper()
        drug = str(row.get("declared_drug") or "") or _ATC_DRUGS.get(atc, _drug_name(drug_cell))
        frequency_values = _frequency_values(parse_child_cell)
        reasons: list[str] = list(row.get("blocking_reasons") or [])
        if len(clauses) != 1:
            reasons.append("MULTIPLE_DOSE_STRATA")
        if frequency_values is None:
            reasons.append("FREQUENCY_NOT_EXTRACTED")
        route_text = " ".join(cells).lower()
        has_iv = "в/в" in route_text or "внутривенно" in route_text
        has_im = "в/м" in route_text or "в/мышечно" in route_text or "внутримышечно" in route_text
        has_oral = "перорально" in route_text or "внутрь" in route_text
        if has_oral and (has_iv or has_im):
            route = "multiple_routes"
            reasons.append("ROUTE_NOT_EXACT")
        elif has_iv and has_im:
            route = "parenteral_unspecified"
            reasons.append("ROUTE_NOT_EXACT")
        elif has_iv:
            route = "intravenous"
        elif has_im:
            route = "intramuscular"
        elif "введени" in parse_child_cell.lower():
            route = "parenteral_unspecified"
            reasons.append("ROUTE_NOT_EXACT")
        else:
            route = "oral"
        dose = clauses[0]
        multiplier = 1000.0 if basis == "FIXED_PER_DOSE" and dose.groupdict().get("unit", "").lower() == "г" else 1.0
        value_min = _number(dose.group("low")) * multiplier
        value_max = _number(dose.group("high") or dose.group("low")) * multiplier
        freq_min, freq_max = frequency_values or (None, None)
        source_wording = f"{drug_cell} — дети: {child_cell}"
        declared_population = row.get("population_constraints_override")
        population_constraints: dict[str, Any] = (
            dict(declared_population) if declared_population is not None else {}
        )
        formulation_required: str | None = None
        if declared_population is None and re.search(r"младше\s*3\s*лет", child_cell, re.IGNORECASE):
            population_constraints["age_years_max_exclusive"] = 3
        older_than = re.search(r"старше\s*(\d+)\s*лет", child_cell, re.IGNORECASE) if declared_population is None else None
        if older_than:
            population_constraints["age_years_min_exclusive"] = int(older_than.group(1))
        from_age = re.search(r"(?:с|от)\s*(\d+)\s*лет", child_cell, re.IGNORECASE) if declared_population is None else None
        if from_age:
            population_constraints["age_years_min_inclusive"] = int(from_age.group(1))
        if "суспензи" in drug_cell.lower():
            formulation_required = "oral_suspension"
        identity = json.dumps(
            [spec.guideline_id, atc, row["page"], row["row"], source_wording],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        candidate_id = "erc_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        row_duration = (
            _clean(cells[int(duration_col)])
            if duration_col is not None and len(cells) > int(duration_col) else ""
        )
        duration = str(row.get("duration_override") or "") or row_duration or spec.duration
        if duration.startswith("NOT_STATED"):
            reasons.append("DURATION_NOT_EXTRACTED")
        if row_duration and ("[сноска" in row_duration.lower() or "#" in row_duration):
            reasons.append("DURATION_FOOTNOTE_REVIEW_REQUIRED")
        secondary_evidence = [] if row_duration else [{
            "page": spec.duration_page,
            "wording": spec.duration_wording,
            "purpose": "duration",
        }]
        candidates.append({
            "candidate_id": candidate_id,
            "review_status": "REVIEW_REQUIRED",
            "calculation_ready": not reasons,
            "blocking_reasons": reasons,
            "guideline": {
                "id": spec.guideline_id,
                "title": spec.guideline_title,
                "approval_year": spec.approval_year,
                "status": "CURRENT",
                "source_url": spec.source_url,
                "pdf_sha256": pdf_sha256,
            },
            "diagnosis": spec.diagnosis,
            "icd10": list(spec.icd10),
            "therapy_line": section,
            "drug": drug,
            "atc": atc,
            "population_constraints": population_constraints,
            "formulation_required": formulation_required,
            "dose": {
                "value_min": value_min,
                "value_max": value_max,
                "unit": unit,
                "basis": basis,
                "route": route,
                "frequency_min_per_day": freq_min,
                "frequency_max_per_day": freq_max,
                "duration": duration,
                "maximum_dose": "NOT_STATED_IN_TABLE_ROW",
            },
            "source": {
                "pdf_path": str(path),
                "page": row["page"],
                "table_index": row["table_index"],
                "table_row": row["row"],
                "table_row_end": row.get("row_end", row["row"]),
                "dose_col": dose_col,
                "wording": source_wording,
                "cells": row["cell_provenance"],
                "secondary_evidence": secondary_evidence,
            },
        })
    return candidates


def write_candidate_artifact(
    output_path: str | Path,
    *,
    pdf_path: str | Path,
    spec: GuidelineCandidateSpec,
) -> Path:
    """Write a deterministic local review artifact (not an approval)."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    actual_sha256 = sha256_file(pdf_path)
    if spec.expected_pdf_sha256 and actual_sha256.lower() != spec.expected_pdf_sha256.lower():
        raise ValueError(
            f"source PDF hash mismatch: expected {spec.expected_pdf_sha256}, got {actual_sha256}"
        )
    candidates = extract_regimen_candidates(pdf_path, spec)
    actual_candidates_sha256 = sha256_json(candidates)
    if (
        spec.expected_candidates_sha256
        and actual_candidates_sha256.lower() != spec.expected_candidates_sha256.lower()
    ):
        raise ValueError(
            "extracted candidate payload mismatch: expected "
            f"{spec.expected_candidates_sha256}, got {actual_candidates_sha256}"
        )
    payload = {
        "schema_version": "1.0.0",
        "artifact_type": "EXTRACTED_REGIMEN_CANDIDATES",
        "guideline_id": spec.guideline_id,
        "source_pdf_sha256": actual_sha256,
        "spec": asdict(spec),
        "candidates_sha256": actual_candidates_sha256,
        "candidates": candidates,
    }
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    return output


def persist_candidate_artifact(
    artifact_path: str | Path,
    kb_path: str | Path,
) -> dict[str, Any]:
    """Persist candidates as queued immutable objects in a Versioned KB."""
    from src.pipeline.knowledge_base import KnowledgeBase

    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    guideline_id = str(artifact["guideline_id"])
    items: list[dict[str, Any]] = []
    for candidate in artifact.get("candidates", []):
        source = candidate["source"]
        dose_col = int(source.get("dose_col", 2))
        primary_cell = next(
            (cell for cell in source.get("cells", []) if cell.get("col") == dose_col),
            (source.get("cells") or [{}])[0],
        )
        bbox = primary_cell.get("bbox")
        provenance = {
            "guideline_id": guideline_id,
            "page": int(source["page"]),
            "bounding_box": (
                {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]}
                if isinstance(bbox, list) and len(bbox) == 4 else None
            ),
            "extractor": "pymupdf",
            "layout_engine": "pymupdf-native-table",
            "semantic_engine": "regimen_candidates.py",
            "table_row": int(source["table_row"]),
            "table_col": int(primary_cell.get("col", dose_col)),
            "table_conf": float(primary_cell.get("confidence", 0.97)),
            "original_text": source["wording"],
            "normalized_value": json.dumps(candidate["dose"], ensure_ascii=False, sort_keys=True),
        }
        content = {key: value for key, value in candidate.items() if key != "source"}
        items.append({
            **content,
            "logical_key": candidate["candidate_id"],
            "confidence": 0.97 if candidate.get("calculation_ready") else 0.70,
            "normalization_status": "normalized" if candidate.get("calculation_ready") else "ambiguous",
            "provenance": provenance,
        })
    document = Document(
        source="pymupdf-native-table",
        pdf_path=Path((artifact.get("candidates") or [{}])[0].get("source", {}).get("pdf_path", "unknown.pdf")),
        pages=[],
        full_text="",
        metadata={"guideline_id": guideline_id},
        knowledge_objects={"RegimenCandidate": items},
    )
    kb = KnowledgeBase(str(kb_path))
    try:
        return kb.add_document(document)
    finally:
        kb.close()


def _table_grid(table: Any) -> list[list[str]]:
    grid = [["" for _ in range(table.cols)] for _ in range(table.rows)]
    for cell in table.cells:
        grid[cell.row][cell.col] = cell.text or ""
    return grid


def _cell_provenance(cell: Any) -> dict[str, Any]:
    bbox = cell.bbox
    return {
        "row": cell.row,
        "col": cell.col,
        "text": cell.text,
        "bbox": [bbox.x0, bbox.y0, bbox.x1, bbox.y1] if bbox else None,
        "engine": cell.engine,
        "confidence": cell.confidence,
    }


def _rows_from_groups(
    rows: Sequence[dict[str, Any]],
    groups: Sequence[CandidateRowGroup],
) -> list[dict[str, Any]]:
    """Assemble only hash-pinned, explicitly declared table row spans."""
    index = {
        (int(row["page"]), int(row["table_index"]), int(row["row"])): row
        for row in rows
    }
    result: list[dict[str, Any]] = []
    for group in groups:
        selected = [
            index.get((group.page, group.table_index, row_number))
            for row_number in range(group.row_start, group.row_end + 1)
        ]
        if any(row is None for row in selected):
            raise ValueError(
                f"source row group missing: page={group.page}, table={group.table_index}, "
                f"rows={group.row_start}-{group.row_end}"
            )
        concrete = [row for row in selected if row is not None]
        width = max(len(row["cells"]) for row in concrete)
        cells = [
            "\n".join(
                _clean(row["cells"][column])
                for row in concrete
                if column < len(row["cells"]) and _clean(row["cells"][column])
            )
            for column in range(width)
        ]
        result.append({
            **concrete[0],
            "row": group.row_start,
            "row_end": group.row_end,
            "cells": cells,
            "cell_provenance": [
                cell
                for row in concrete
                for cell in row["cell_provenance"]
            ],
            "drug_col": group.drug_col,
            "dose_col": group.dose_col,
            "duration_col": group.duration_col,
            "therapy_line": group.therapy_line,
            "blocking_reasons": list(group.blocking_reasons),
            "declared_atc": group.atc,
            "declared_drug": group.drug,
            "duration_override": group.duration,
            "population_constraints_override": group.population_constraints,
        })
    return result


def _join_continuation_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in rows:
        row = {**raw, "cells": list(raw["cells"]), "cell_provenance": list(raw["cell_provenance"])}
        first = _clean(row["cells"][0] if row["cells"] else "")
        previous = result[-1] if result else None
        previous_first = _clean(previous["cells"][0]) if previous else ""
        is_atc_continuation = bool(previous and first.upper().startswith("АТХ") and "КОД" in previous_first.upper())
        is_text_continuation = bool(
            previous
            and not _ATC.search(first)
            and not first.lower().startswith(("при аллергии", "препараты", "альтернативные"))
            and (previous_first.rstrip().endswith(("для", "код")) or _clean(previous["cells"][2]).rstrip().endswith("-"))
        )
        if is_atc_continuation or is_text_continuation:
            previous["cells"] = [
                _join_text(left, right)
                for left, right in zip(previous["cells"], row["cells"])
            ]
            previous["cell_provenance"].extend(row["cell_provenance"])
            previous.setdefault("continued_on_pages", []).append(row["page"])
            continue
        result.append(row)
    return result


def _join_text(left: str, right: str) -> str:
    left, right = left or "", right or ""
    if left.rstrip().endswith("-"):
        # Numeric ``2-`` + ``3 приема`` is a real range, while a split word
        # such as ``Клавулан-`` + ``овая`` should lose the layout hyphen.
        if re.search(r"\d\s*-$", left.rstrip()) and re.match(r"\d", right.lstrip()):
            return left.rstrip() + right.lstrip()
        return left.rstrip()[:-1] + right.lstrip()
    return (left.rstrip() + "\n" + right.lstrip()).strip()


def _clean(value: str) -> str:
    value = _FOOTNOTE.sub(r"[сноска \1]", value or "")
    return re.sub(r"[ \t]+", " ", value).strip()


def _drug_name(value: str) -> str:
    name = re.split(r"\*\*|\(\s*Код\s+АТХ", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return re.sub(r"\s+", " ", name.replace("\n", " ")).strip(" #")


def _number(value: str) -> float:
    return float(value.replace(",", "."))


def _frequency_values(value: str) -> tuple[int, int] | None:
    direct = _FREQUENCY.search(value)
    if direct:
        low = int(direct.group("low"))
        return low, int(direct.group("high") or low)
    alternative = re.search(
        r"(?:в|на|по)\s*(\d+)\s*(?:или|/)\s*(\d+)\s*(?:при[её]м|введени)",
        value,
        re.IGNORECASE,
    )
    if alternative:
        values = sorted((int(alternative.group(1)), int(alternative.group(2))))
        return values[0], values[1]
    once_daily = re.search(r"(\d+)\s*раз(?:а)?\s*в\s*сут", value, re.IGNORECASE)
    if once_daily:
        count = int(once_daily.group(1))
        return count, count
    compact = re.search(r"(\d+)\s*(?:[-–—]\s*(\d+))?\s*р(?:аз(?:а)?)?\s*/\s*сут", value, re.IGNORECASE)
    if compact:
        low = int(compact.group(1))
        high = int(compact.group(2) or low)
        return min(low, high), max(low, high)
    hours = re.search(
        r"каждые\s*(\d+)\s*(?:[-–—]\s*(\d+))?\s*(?:час(?:а|ов)?|ч\b)",
        value,
        re.IGNORECASE,
    )
    if hours:
        low_hours = int(hours.group(1))
        high_hours = int(hours.group(2) or low_hours)
        return 24 // max(low_hours, high_hours), 24 // min(low_hours, high_hours)
    if re.search(r"однократно", value, re.IGNORECASE):
        return 1, 1
    return None


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build queued regimen candidates from a verified PDF")
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kb", type=Path)
    args = parser.parse_args(argv)
    spec = load_candidate_spec(args.spec)
    artifact = write_candidate_artifact(args.output, pdf_path=args.pdf, spec=spec)
    result: dict[str, Any] = {
        "artifact": str(artifact),
        "candidate_count": len(json.loads(artifact.read_text(encoding="utf-8"))["candidates"]),
    }
    if args.kb:
        result["knowledge_base"] = persist_candidate_artifact(artifact, args.kb)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "CandidateRowGroup",
    "GuidelineCandidateSpec",
    "candidate_spec_from_mapping",
    "extract_regimen_candidates",
    "load_candidate_spec",
    "persist_candidate_artifact",
    "sha256_file",
    "sha256_json",
    "write_candidate_artifact",
]


if __name__ == "__main__":
    raise SystemExit(_main())
