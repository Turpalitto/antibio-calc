"""Fail-close calculator records without a pinned guideline source spec."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


DEFAULT_REASON = (
    "Расчёт временно закрыт: для этой нозологии ещё не закреплены актуальная "
    "карточка КР, полный PDF и проверенный набор схем дозирования."
)


def apply_source_gate(db: dict[str, Any], specs_dir: str | Path) -> dict[str, int]:
    specs = {
        str(raw.get("guideline_id"))
        for path in Path(specs_dir).glob("*.json")
        for raw in [json.loads(path.read_text(encoding="utf-8"))]
        if raw.get("guideline_id")
    }
    added = already_blocked = covered = 0
    for disease in db.get("recommendations", []):
        if disease.get("calculation_blocked"):
            already_blocked += 1
        elif (
            str(disease.get("cr_id") or "") in specs
            and disease.get("source_verification_status") == "CALCULATOR_BOUND_VERIFIED"
        ):
            covered += 1
        else:
            disease["calculation_blocked"] = True
            disease["source_verification_status"] = (
                "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
                if str(disease.get("cr_id") or "") in specs
                else "SOURCE_SPEC_MISSING"
            )
            disease["calculation_block_reason"] = DEFAULT_REASON
            added += 1
    return {"covered_unblocked": covered, "already_blocked": already_blocked, "newly_blocked": added}


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply calculator source fail-closed gate")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--specs", required=True, type=Path)
    args = parser.parse_args(argv)
    db = json.loads(args.db.read_text(encoding="utf-8-sig"))
    stats = apply_source_gate(db, args.specs)
    args.db.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["DEFAULT_REASON", "apply_source_gate"]
