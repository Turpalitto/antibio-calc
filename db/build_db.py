#!/usr/bin/env python
"""Cross-platform port of db/build_db.ps1 (no pwsh on macOS).

Mirrors the Windows PowerShell build exactly:
  1. load db/index.json -> meta + drugs_reference
  2. glob db/diseases/*.json (each {category, recommendations[]}) sorted by
     filename, collecting categories=[{file, category, count}] and appending
     all recommendations
  3. write db/antibio_db.json = {meta, drugs_reference, categories,
     recommendations} as UTF-8 no-BOM compact (no trailing newline), matching
     ConvertTo-Json -Depth 12 -Compress
  4. FAIL-CLOSED source gate: run calculator_source_gate.py --db <outFile>
     --specs clinical_sources/regimen_candidate_specs; raise if non-zero exit
  5. optional integrity gate: run node db/validate_db.js; raise if non-zero

The whole point is that db/diseases/*.json records do NOT carry
calculation_blocked / source_verification_status / calculation_block_reason;
those are added by the source gate at build time. This module never marks
anything clinically approved.

Usage:
    .venv/bin/python db/build_db.py --db db/antibio_db.json \
        --diseases db/diseases --specs clinical_sources/regimen_candidate_specs \
        --index db/index.json [--skip-source-gate] [--skip-validate]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_db(
    index_path: Path,
    diseases_dir: Path,
    *,
    output_path: Path,
    specs_dir: Path | None = None,
    python_exe: str | None = None,
    run_source_gate: bool = True,
    run_validate: bool = True,
    node_exe: str | None = None,
) -> dict[str, Any]:
    """Assemble db/antibio_db.json from index + diseases, then run the gates."""
    index = _load_json(index_path)
    meta = index["meta"]
    drugs_reference = index["drugs_reference"]

    disease_files = sorted(diseases_dir.glob("*.json"), key=lambda p: p.name)
    categories: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    for df in disease_files:
        data = _load_json(df)
        recs = data.get("recommendations", [])
        categories.append(
            {"file": df.name, "category": data["category"], "count": len(recs)}
        )
        recommendations.extend(recs)

    db: dict[str, Any] = {
        "meta": meta,
        "drugs_reference": drugs_reference,
        "categories": categories,
        "recommendations": recommendations,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
    output_path.write_text(payload, encoding="utf-8")

    if run_source_gate and specs_dir is not None:
        _run_source_gate(output_path, specs_dir, python_exe)
        # re-read because the gate mutated the file in place
        db = _load_json(output_path)

    if run_validate:
        _run_validate(output_path, node_exe)

    return db


def _run_source_gate(
    output_path: Path, specs_dir: Path, python_exe: str | None
) -> None:
    py = python_exe or sys.executable
    gate = PROJECT_ROOT / "src" / "pipeline" / "extraction" / "calculator_source_gate.py"
    cmd = [py, str(gate), "--db", str(output_path), "--specs", str(specs_dir)]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "calculator_source_gate.py failed (exit %d):\n%s"
            % (result.returncode, result.stderr or result.stdout)
        )


def _run_validate(output_path: Path, node_exe: str | None) -> None:
    node = node_exe or "node"
    validator = PROJECT_ROOT / "db" / "validate_db.js"
    result = subprocess.run(
        [node, "db/validate_db.js"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "db/validate_db.js failed (exit %d):\n%s"
            % (result.returncode, result.stderr or result.stdout)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build db/antibio_db.json (Python port of build_db.ps1)")
    parser.add_argument("--db", default="db/antibio_db.json", help="output db path")
    parser.add_argument("--diseases", default="db/diseases", help="diseases dir")
    parser.add_argument("--index", default="db/index.json", help="index.json path")
    parser.add_argument("--specs", default="clinical_sources/regimen_candidate_specs", help="specs dir for source gate")
    parser.add_argument("--skip-source-gate", action="store_true")
    parser.add_argument("--skip-validate", action="store_true")
    args = parser.parse_args(argv)

    root = Path.cwd() if (Path.cwd() / "db").exists() else PROJECT_ROOT
    db = build_db(
        root / args.index,
        root / args.diseases,
        output_path=root / args.db,
        specs_dir=root / args.specs,
        run_source_gate=not args.skip_source_gate,
        run_validate=not args.skip_validate,
    )
    print(
        json.dumps(
            {
                "recommendations": len(db["recommendations"]),
                "categories": len(db["categories"]),
                "drugs_reference": len(db["drugs_reference"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
