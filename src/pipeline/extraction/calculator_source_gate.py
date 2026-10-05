"""Calculator source gate: block records explicitly marked as unverified in source.

Policy (2026-10-05, owner decision — see DECISIONS.md):
- ``unblock_all=True``  -> escape hatch: nothing is blocked.
- default               -> a record is blocked ONLY when the source marks it:
  ``calculation_blocked: true`` or a non-verified ``source_verification_status``.
  Unmarked records stay computable; ``CALCULATOR_BOUND_VERIFIED`` records are
  left untouched. The gate never clears an explicit source block.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


DEFAULT_REASON = (
    "Расчёт временно закрыт: для этой нозологии ещё не закреплены актуальная "
    "карточка КР, полный PDF и проверенный набор схем дозирования."
)


def apply_source_gate(
    db: dict[str, Any],
    specs_dir: str | Path,
    unblock_all: bool = False,
) -> dict[str, int]:
    specs = {
        str(raw.get("guideline_id"))
        for path in Path(specs_dir).glob("*.json")
        for raw in [json.loads(path.read_text(encoding="utf-8"))]
        if raw.get("guideline_id")
    }
    added = already_blocked = covered = 0
    for disease in db.get("recommendations", []):
        cr_id = str(disease.get("cr_id") or "")
        is_verified = (
            cr_id in specs
            and disease.get("source_verification_status") == "CALCULATOR_BOUND_VERIFIED"
        )
        if unblock_all:
            disease["calculation_blocked"] = False
            if is_verified:
                disease["source_verification_status"] = "CALCULATOR_BOUND_VERIFIED"
            elif cr_id in specs:
                disease["source_verification_status"] = "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
            else:
                disease["source_verification_status"] = "CR_REFERENCE_CALCULATION"
            disease.pop("calculation_block_reason", None)
            covered += 1
        else:
            status = disease.get("source_verification_status")
            explicitly_marked = disease.get("calculation_blocked") is True or (
                status is not None and status != "CALCULATOR_BOUND_VERIFIED"
            )
            if explicitly_marked:
                if disease.get("calculation_blocked") is True:
                    already_blocked += 1
                else:
                    disease["calculation_blocked"] = True
                    added += 1
                disease.setdefault("calculation_block_reason", DEFAULT_REASON)
                disease.setdefault(
                    "source_verification_status",
                    "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
                    if cr_id in specs
                    else "SOURCE_SPEC_MISSING",
                )
            elif is_verified:
                covered += 1
            else:
                disease["calculation_blocked"] = False
                disease["source_verification_status"] = (
                    "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
                    if cr_id in specs
                    else "CR_REFERENCE_CALCULATION"
                )
                disease.pop("calculation_block_reason", None)
                covered += 1
    return {"covered_unblocked": covered, "already_blocked": already_blocked, "newly_blocked": added}


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply calculator source fail-closed gate")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--specs", required=True, type=Path)
    parser.add_argument("--unblock-all", action="store_true", default=False, help="Unblock all recommendations for calculation")
    args = parser.parse_args(argv)
    db = json.loads(args.db.read_text(encoding="utf-8-sig"))
    stats = apply_source_gate(db, args.specs, unblock_all=args.unblock_all)
    args.db.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["DEFAULT_REASON", "apply_source_gate"]
