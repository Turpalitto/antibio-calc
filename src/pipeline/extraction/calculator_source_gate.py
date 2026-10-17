"""Calculator source gate: decide, per disease record, whether the calculator may compute.

Policy (2026-10-05, owner decision — see DECISIONS.md), amended 2026-10-14 after the
calculator audit (docs/audits/AUDIT_2026-10-14.md, findings B-2 / B-7):

- ``unblock_all=True``  -> escape hatch: nothing is blocked.
- default               -> a record is blocked when the source marks it:
  ``calculation_blocked: true`` or a non-verified ``source_verification_status``.
  The gate never clears an explicit source block.
- every record leaves the gate with an explicit boolean ``calculation_blocked``
  (the shell treats a missing key as "not blocked", so an implicit value is a
  silent policy decision — B-7).
- a record whose ``cr_id`` is not a federal clinical-guideline identifier
  (``^\\d+(_\\d+)?$``) is never labelled ``CR_REFERENCE_CALCULATION`` (B-2):
    * with a documented basis (``cr_note``)  -> ``NO_FEDERAL_CR_EXPERT_BASIS``,
      still computable, the shell shows the basis in an amber banner;
    * without any documented basis           -> blocked, ``SOURCE_BASIS_MISSING``.
  ``block_no_cr=True`` (CLI ``--block-no-cr``) blocks the ``cr_note`` records too;
  the owner can flip the default once the no-CR schemes have been re-reviewed.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence

DEFAULT_REASON = (
    "Расчёт временно закрыт: для этой нозологии ещё не закреплены актуальная "
    "карточка КР, полный PDF и проверенный набор схем дозирования."
)
NO_BASIS_REASON = (
    "Расчёт закрыт: у записи нет ни идентификатора федеральной КР (cr_id), ни "
    "документированного основания схемы (cr_note). Владелец должен указать источник."
)
NO_CR_POLICY_REASON = (
    "Расчёт закрыт политикой сборки (--block-no-cr): схема не привязана к федеральной КР."
)

STATUS_VERIFIED = "CALCULATOR_BOUND_VERIFIED"
STATUS_SPEC_PENDING = "SOURCE_SPEC_PENDING_CALCULATOR_BINDING"
STATUS_CR_REFERENCE = "CR_REFERENCE_CALCULATION"
STATUS_NO_CR_EXPERT = "NO_FEDERAL_CR_EXPERT_BASIS"
STATUS_BASIS_MISSING = "SOURCE_BASIS_MISSING"
STATUS_SPEC_MISSING = "SOURCE_SPEC_MISSING"

# Federal CR rubricator identifiers as used in this repository: "314", "313_3", "66_4".
_CR_ID_RE = re.compile(r"^\d+(?:_\d+)?$")

# Statuses the gate itself assigns to *computable* records. They are the gate's own
# output, not a source mark, so re-running the gate on an already gated database
# must not turn them into blocks (idempotence).
GATE_COMPUTABLE_STATUSES = frozenset({STATUS_SPEC_PENDING, STATUS_CR_REFERENCE, STATUS_NO_CR_EXPERT})


def is_federal_cr_id(value: Any) -> bool:
    """True when ``value`` looks like a federal CR rubricator id ("314", "313_3")."""
    return bool(_CR_ID_RE.match(str(value or "").strip()))


def has_documented_basis(disease: dict[str, Any]) -> bool:
    """True when the record documents the basis of its schemes outside a federal CR."""
    return bool(str(disease.get("cr_note") or "").strip())


def _load_specs(specs_dir: str | Path) -> set[str]:
    return {
        str(raw.get("guideline_id"))
        for path in Path(specs_dir).glob("*.json")
        for raw in [json.loads(path.read_text(encoding="utf-8"))]
        if raw.get("guideline_id")
    }


def _computable_status(disease: dict[str, Any], specs: set[str]) -> str:
    """Status of a record that carries no explicit source mark."""
    cr_id = str(disease.get("cr_id") or "").strip()
    if cr_id in specs:
        return STATUS_SPEC_PENDING
    if is_federal_cr_id(cr_id):
        return STATUS_CR_REFERENCE
    if has_documented_basis(disease):
        return STATUS_NO_CR_EXPERT
    return STATUS_BASIS_MISSING


def apply_source_gate(
    db: dict[str, Any],
    specs_dir: str | Path,
    unblock_all: bool = False,
    block_no_cr: bool = False,
) -> dict[str, int]:
    specs = _load_specs(specs_dir)
    added = already_blocked = covered = 0
    no_cr_expert = basis_missing = 0
    for disease in db.get("recommendations", []):
        cr_id = str(disease.get("cr_id") or "").strip()
        is_verified = cr_id in specs and disease.get("source_verification_status") == STATUS_VERIFIED
        if unblock_all:
            disease["calculation_blocked"] = False
            disease["source_verification_status"] = (
                STATUS_VERIFIED if is_verified else _computable_status(disease, specs)
            )
            disease.pop("calculation_block_reason", None)
            covered += 1
            continue

        status = disease.get("source_verification_status")
        explicitly_marked = disease.get("calculation_blocked") is True or (
            status is not None
            and status != STATUS_VERIFIED
            and status not in GATE_COMPUTABLE_STATUSES
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
                STATUS_SPEC_PENDING if cr_id in specs else STATUS_SPEC_MISSING,
            )
            continue

        if is_verified:
            disease["calculation_blocked"] = False
            disease.pop("calculation_block_reason", None)
            covered += 1
            continue

        computable_status = _computable_status(disease, specs)
        disease["source_verification_status"] = computable_status
        if computable_status == STATUS_BASIS_MISSING:
            disease["calculation_blocked"] = True
            disease["calculation_block_reason"] = NO_BASIS_REASON
            basis_missing += 1
            added += 1
        elif computable_status == STATUS_NO_CR_EXPERT and block_no_cr:
            disease["calculation_blocked"] = True
            disease["calculation_block_reason"] = NO_CR_POLICY_REASON
            no_cr_expert += 1
            added += 1
        else:
            disease["calculation_blocked"] = False
            disease.pop("calculation_block_reason", None)
            if computable_status == STATUS_NO_CR_EXPERT:
                no_cr_expert += 1
            covered += 1
    return {
        "covered_unblocked": covered,
        "already_blocked": already_blocked,
        "newly_blocked": added,
        "no_cr_expert_basis": no_cr_expert,
        "basis_missing_blocked": basis_missing,
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply calculator source fail-closed gate")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--specs", required=True, type=Path)
    parser.add_argument("--unblock-all", action="store_true", default=False, help="Unblock all recommendations for calculation")
    parser.add_argument(
        "--block-no-cr",
        action="store_true",
        default=False,
        help="Also block records that have no federal CR id even when they document their basis (cr_note)",
    )
    args = parser.parse_args(argv)
    db = json.loads(args.db.read_text(encoding="utf-8-sig"))
    stats = apply_source_gate(db, args.specs, unblock_all=args.unblock_all, block_no_cr=args.block_no_cr)
    args.db.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "DEFAULT_REASON",
    "GATE_COMPUTABLE_STATUSES",
    "NO_BASIS_REASON",
    "NO_CR_POLICY_REASON",
    "STATUS_BASIS_MISSING",
    "STATUS_CR_REFERENCE",
    "STATUS_NO_CR_EXPERT",
    "STATUS_SPEC_MISSING",
    "STATUS_SPEC_PENDING",
    "STATUS_VERIFIED",
    "apply_source_gate",
    "has_documented_basis",
    "is_federal_cr_id",
]
