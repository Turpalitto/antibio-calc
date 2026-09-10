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

if str(PROJECT_ROOT) not in sys.path:  # allow `python db/build_db.py` from anywhere
    sys.path.insert(0, str(PROJECT_ROOT))

from clinical_engine.crosswalk import (  # noqa: E402
    CrosswalkBuildError,
    DEFAULT_OUTPUT as DEFAULT_CROSSWALK_PATH,
    build_crosswalk_from_paths,
    compact_links,
    crosswalk_summary,
)
from clinical_engine.crosswalk.builder import DEFAULT_DIAGNOSIS_INDEX  # noqa: E402


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def attach_guideline_links(
    db: dict[str, Any],
    *,
    calculator_db_path: Path,
    diagnosis_index_path: Path = DEFAULT_DIAGNOSIS_INDEX,
    crosswalk_path: Path = DEFAULT_CROSSWALK_PATH,
    check_committed: bool = True,
) -> dict[str, int]:
    """Embed the КР corpus crosswalk into the calculator database (in place).

    Fail-closed: the committed ``calculator_crosswalk.json`` must exist and must
    match a fresh rebuild from the current inputs, otherwise the build aborts
    rather than embedding stale provenance. Set ``check_committed=False`` only
    from tests that build throwaway fixture databases.

    Adds ``recommendations[].guideline_links`` and ``meta.guideline_crosswalk``.
    Neither field is clinical approval and neither unblocks calculation.
    """
    rebuilt = build_crosswalk_from_paths(calculator_db_path, diagnosis_index_path)
    if check_committed:
        if not Path(crosswalk_path).is_file():
            raise CrosswalkBuildError(
                f"crosswalk artifact missing: {crosswalk_path} — run "
                "`python -m clinical_engine.crosswalk --write`"
            )
        expected = json.dumps(rebuilt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if Path(crosswalk_path).read_text(encoding="utf-8") != expected:
            raise CrosswalkBuildError(
                f"crosswalk artifact is stale: {crosswalk_path} — run "
                "`python -m clinical_engine.crosswalk --write`"
            )

    links_by_disease = compact_links(rebuilt)
    attached = 0
    for disease in db.get("recommendations", []):
        links = links_by_disease.get(str(disease.get("id")), [])
        disease["guideline_links"] = links
        if links:
            attached += 1
    meta = db.setdefault("meta", {})
    meta["guideline_crosswalk"] = crosswalk_summary(rebuilt)
    return {
        "diseases": len(db.get("recommendations", [])),
        "diseases_with_links": attached,
        "links": len(rebuilt.get("links", [])),
    }


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
    attach_crosswalk: bool = True,
    crosswalk_check_committed: bool = True,
    diagnosis_index_path: Path = DEFAULT_DIAGNOSIS_INDEX,
    crosswalk_path: Path = DEFAULT_CROSSWALK_PATH,
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

    if attach_crosswalk:
        # The crosswalk reads the file on disk (post source-gate) so that the
        # provenance it records matches exactly what ships in the build.
        attach_guideline_links(
            db,
            calculator_db_path=output_path,
            diagnosis_index_path=diagnosis_index_path,
            crosswalk_path=crosswalk_path,
            check_committed=crosswalk_check_committed,
        )
        payload = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
        output_path.write_text(payload, encoding="utf-8")

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
    parser.add_argument("--diagnosis-index", default=str(DEFAULT_DIAGNOSIS_INDEX), help="corpus diagnosis index used for the КР crosswalk")
    parser.add_argument("--crosswalk", default=str(DEFAULT_CROSSWALK_PATH), help="committed crosswalk artifact")
    parser.add_argument("--skip-source-gate", action="store_true")
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--skip-crosswalk", action="store_true", help="do not embed КР corpus links (diagnostics only)")
    parser.add_argument(
        "--attach-only",
        action="store_true",
        help="do not rebuild: only embed the КР crosswalk into an existing db (used by build_db.ps1)",
    )
    args = parser.parse_args(argv)

    root = Path.cwd() if (Path.cwd() / "db").exists() else PROJECT_ROOT

    if args.attach_only:
        db_path = root / args.db
        db = _load_json(db_path)
        stats = attach_guideline_links(
            db,
            calculator_db_path=db_path,
            diagnosis_index_path=Path(args.diagnosis_index),
            crosswalk_path=Path(args.crosswalk),
        )
        db_path.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(json.dumps({"attached": stats}, ensure_ascii=False, sort_keys=True))
        return 0

    db = build_db(
        root / args.index,
        root / args.diseases,
        output_path=root / args.db,
        specs_dir=root / args.specs,
        run_source_gate=not args.skip_source_gate,
        run_validate=not args.skip_validate,
        attach_crosswalk=not args.skip_crosswalk,
        diagnosis_index_path=Path(args.diagnosis_index),
        crosswalk_path=Path(args.crosswalk),
    )
    linked = sum(1 for r in db["recommendations"] if r.get("guideline_links"))
    print(
        json.dumps(
            {
                "recommendations": len(db["recommendations"]),
                "categories": len(db["categories"]),
                "drugs_reference": len(db["drugs_reference"]),
                "recommendations_with_guideline_links": linked,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
