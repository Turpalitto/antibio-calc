"""Build a reproducible calculator-to-guideline source inventory.

This is an audit artifact, not clinical approval. Rubricator metadata from the
local corpus is only a discovery hint until the official card is checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

import fitz


def build_source_inventory(
    db_path: str | Path,
    clinrecs_path: str | Path,
    corpus_roots: Iterable[str | Path],
) -> dict[str, Any]:
    db = json.loads(Path(db_path).read_text(encoding="utf-8-sig"))
    clinrecs = json.loads(Path(clinrecs_path).read_text(encoding="utf-8-sig"))
    roots = [Path(root) for root in corpus_roots]
    by_code: dict[str, list[dict[str, Any]]] = {}
    by_code_version: dict[str, list[dict[str, Any]]] = {}
    for item in clinrecs:
        by_code.setdefault(str(item.get("Code") or ""), []).append(item)
        by_code_version.setdefault(str(item.get("CodeVersion") or ""), []).append(item)

    rows: list[dict[str, Any]] = []
    for disease in db.get("recommendations", []):
        declared = str(disease.get("cr_id") or "").strip()
        if not declared or declared in {"—", "-"}:
            matches: list[dict[str, Any]] = []
            match_basis = "NO_DECLARED_CR_ID"
        elif "_" in declared:
            matches = by_code_version.get(declared, [])
            match_basis = "EXACT_CODE_VERSION"
        else:
            matches = by_code.get(declared, [])
            match_basis = "CODE_LATEST_VERSION"
        selected = _latest(matches)
        pdf = _find_pdf(selected, roots) if selected else None
        pdf_info = _pdf_info(pdf) if pdf else None
        rows.append({
            "disease_id": disease.get("id"),
            "disease_name": disease.get("name"),
            "declared_cr_id": declared,
            "declared_cr_year": disease.get("cr_year"),
            "declared_source_url": disease.get("source_url"),
            "calculation_blocked": bool(disease.get("calculation_blocked")),
            "metadata_match_basis": match_basis,
            "metadata_match_count": len(matches),
            "latest_local_metadata": _metadata(selected),
            "local_pdf": pdf_info,
            "official_card_status": "NOT_YET_CHECKED",
            "source_contract_status": "NOT_YET_PINNED",
        })
    return {
        "schema_version": "1.0.0",
        "artifact_type": "CALCULATOR_SOURCE_INVENTORY",
        "warning": "Local corpus metadata is discovery evidence only; verify official rubricator card and PDF before clinical use.",
        "disease_count": len(rows),
        "declared_cr_id_count": sum(bool(row["declared_cr_id"] and row["declared_cr_id"] not in {"—", "-"}) for row in rows),
        "metadata_match_count": sum(row["latest_local_metadata"] is not None for row in rows),
        "local_pdf_count": sum(row["local_pdf"] is not None for row in rows),
        "rows": rows,
    }


def _latest(items: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return max(items, key=lambda item: (int(item.get("Version") or 0), str(item.get("CreatedStr") or ""), int(item.get("Id") or 0)))


def _metadata(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {key: item.get(key) for key in (
        "Id", "Name", "Code", "Version", "CodeVersion", "Status",
        "AgeCategoryStr", "CreatedStr", "pdf_path", "pdf_size",
        "has_antibiotics", "has_dosing_info", "has_duration_info",
    )}


def _find_pdf(item: dict[str, Any], roots: Sequence[Path]) -> Path | None:
    name = str(item.get("Name") or "").strip()
    preferred = Path(str(item.get("pdf_path") or "")).name
    names = [candidate for candidate in (preferred, f"{name}.pdf") if candidate]
    for root in roots:
        for candidate in names:
            path = root / candidate
            if path.is_file():
                return path.resolve()
    return None


def _pdf_info(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        document = fitz.open(path)
        pages = len(document)
        document.close()
        valid = True
    except Exception:
        pages = None
        valid = False
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": f"sha256:{digest}",
        "page_count": pages,
        "pdf_open_ok": valid,
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory calculator guideline sources")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--clinrecs", required=True, type=Path)
    parser.add_argument("--corpus-root", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_source_inventory(args.db, args.clinrecs, args.corpus_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in (
        "disease_count", "declared_cr_id_count", "metadata_match_count", "local_pdf_count"
    )}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["build_source_inventory"]
