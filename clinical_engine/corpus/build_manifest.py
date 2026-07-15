"""Build reason-coded corpus manifest from external read-only metadata.

No document is automatically added to or removed from the certified KB.
Unselected antibiotic-flagged documents become REVIEW_REQUIRED.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clinical_engine.corpus.locator import CorpusLocator


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _selected(root: Path) -> set[str]:
    knowledge_base = root / "knowledge_base.json"
    records = json.loads(knowledge_base.read_text(encoding="utf-8-sig"))
    names = {str(record["pdf_file"]) for record in records if record.get("pdf_file")}
    return {
        name
        for name in names
        if any((root / directory / name).is_file() for directory in ("downloads_active", "archive_review"))
    }


def _locations(root: Path, name: str, metadata_paths: set[str]) -> list[Path]:
    candidates = [Path(value) for value in metadata_paths if value]
    candidates.extend(root / directory / name for directory in (
        "downloads_active", "archive_review", "archive_no_antibiotics", "downloads_other"
    ))
    unique: dict[str, Path] = {}
    for candidate in candidates:
        if candidate.is_file() and candidate.name == name:
            unique[str(candidate.resolve()).casefold()] = candidate.resolve()
    return sorted(unique.values(), key=lambda value: str(value).casefold())


def build(locator: CorpusLocator | None = None) -> dict[str, Any]:
    locator = locator or CorpusLocator()
    root = locator.root.resolve()
    selected = _selected(root)
    with closing(locator.open_metadata()) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, name, status, pdf_path, abx_drugs, has_antibiotics "
            "FROM clinrecs WHERE trim(coalesce(abx_drugs, '')) <> ''"
        ).fetchall()

    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        if row["pdf_path"]:
            grouped[Path(str(row["pdf_path"])).name].append(row)

    universe = sorted(set(grouped) | selected, key=str.casefold)
    generated_at = datetime.now(timezone.utc).isoformat()
    documents: list[dict[str, Any]] = []
    for name in universe:
        source_rows = grouped.get(name, [])
        paths = _locations(root, name, {str(row["pdf_path"] or "") for row in source_rows})
        if not paths:
            raise FileNotFoundError(f"Corpus document has no readable source file: {name}")
        hashes = {_sha256(path) for path in paths}
        if len(hashes) != 1:
            raise ValueError(f"Same corpus filename has conflicting content hashes: {name}")
        included = name in selected
        relevance = (
            "METADATA_ABX_DRUGS_NONEMPTY"
            if source_rows
            else "P4_4_BUILDER_SELECTED_WITHOUT_ABX_DRUGS_FLAG"
        )
        documents.append({
            "file": name,
            "sha256": next(iter(hashes)),
            "guideline_ids": sorted({str(row["id"]) for row in source_rows}),
            "titles": sorted({str(row["name"]) for row in source_rows}),
            "antibiotic_relevance": relevance,
            "inclusion_state": "INCLUDED" if included else "REVIEW_REQUIRED",
            "exclusion_reason": None,
            "reviewer": None,
            "evidence": (
                "Present in P4.4 builder selection (downloads_active/archive_review)."
                if included
                else "Non-empty metadata abx_drugs flag, absent from P4.4 builder selection; clinical adjudication required."
            ),
            "date": generated_at,
            "source_locations": [str(path) for path in paths],
        })

    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "source_root": str(root),
        "selection_contract": "build_p44_kb.load_contributing_pdfs",
        "documents": documents,
        "summary": {
            "total": len(documents),
            "included": sum(item["inclusion_state"] == "INCLUDED" for item in documents),
            "review_required": sum(item["inclusion_state"] == "REVIEW_REQUIRED" for item in documents),
            "excluded": sum(item["inclusion_state"].startswith("EXCLUDED_") for item in documents),
        },
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="CORPUS_MANIFEST.json")
    args = parser.parse_args()
    Path(args.out).write_text(json.dumps(build(), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
