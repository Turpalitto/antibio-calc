"""Audit calculator diseases against verified PDF regimen-candidate specs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def audit_source_coverage(db_path: str | Path, specs_dir: str | Path) -> dict[str, Any]:
    db = json.loads(Path(db_path).read_text(encoding="utf-8-sig"))
    specs: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(specs_dir).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        guideline_id = str(raw.get("guideline_id") or "")
        if not guideline_id:
            raise ValueError(f"{path}: guideline_id missing")
        if guideline_id in specs:
            raise ValueError(f"duplicate guideline_id spec: {guideline_id}")
        specs[guideline_id] = raw

    rows: list[dict[str, Any]] = []
    for disease in db.get("recommendations", []):
        cr_id = str(disease.get("cr_id") or "")
        spec = specs.get(cr_id)
        if spec and disease.get("calculation_blocked"):
            source_status = "VERIFIED_SPEC_CALCULATION_BLOCKED"
        elif spec:
            source_status = "VERIFIED_SPEC"
        elif disease.get("calculation_blocked"):
            source_status = "SOURCE_BLOCKED"
        else:
            source_status = "MISSING_SPEC"
        rows.append({
            "disease_id": disease.get("id"),
            "name": disease.get("name"),
            "cr_id": cr_id,
            "cr_year": disease.get("cr_year"),
            "source_spec_status": source_status,
            "calculation_block_reason": disease.get("calculation_block_reason"),
            "rubricator_revision": spec.get("rubricator_revision") if spec else None,
            "expected_pdf_sha256": spec.get("expected_pdf_sha256") if spec else None,
        })
    covered = sum(row["source_spec_status"].startswith("VERIFIED_SPEC") for row in rows)
    blocked = sum(bool(row["calculation_block_reason"]) for row in rows)
    unblocked_missing = sum(row["source_spec_status"] == "MISSING_SPEC" for row in rows)
    return {
        "schema_version": "1.0.0",
        "disease_count": len(rows),
        "verified_spec_disease_count": covered,
        "missing_spec_disease_count": len(rows) - covered,
        "source_blocked_disease_count": blocked,
        "unblocked_missing_spec_disease_count": unblocked_missing,
        "unique_spec_count": len(specs),
        "rows": rows,
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit PDF-source coverage of calculator diseases")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--specs", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = audit_source_coverage(args.db, args.specs)
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["audit_source_coverage"]
