#!/usr/bin/env python
"""Why is calculation blocked, and what exactly is missing?

``calculator_source_gate.py`` fail-closes every nozology that has no pinned
КР source spec. As of 2026-09-10 that is 119 of 120 records, which makes the
calculator look broken when it is actually behaving as designed. This tool turns
the block into a worklist: for every disease it states the current status, which
artifacts are already pinned, and the single next action the owner has to take.

It never unblocks anything and never writes to ``db/``.

Usage:
    python db/source_gate_report.py                     # summary on stdout
    python db/source_gate_report.py --json out.json     # machine-readable report
    python db/source_gate_report.py --strict            # exit 1 on policy breach
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "antibio_db.json"
SPECS_DIR = PROJECT_ROOT / "clinical_sources" / "regimen_candidate_specs"
DEFAULT_REPORT = PROJECT_ROOT / "generated" / "source_gate_report.json"

# Ordered remediation ladder. The first status that applies is the next action.
NEXT_ACTION = {
    "CALCULATOR_BOUND_VERIFIED": "NONE — расчёт открыт",
    "SOURCE_SPEC_PENDING_CALCULATOR_BINDING": (
        "SPEC_PINNED — карточка КР и PDF закреплены; осталось подтвердить привязку "
        "схем к калькулятору (calculator binding) и перевести статус в "
        "CALCULATOR_BOUND_VERIFIED"
    ),
    "EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW": (
        "OWNER_REVIEW — извлечённые из PDF строки ждут подтверждения врачом в "
        "личном режиме (/v2/personal/extracted-candidates/<guideline_id>)"
    ),
    "CURRENT_WEB_CONFIRMED_PDF_PENDING": (
        "PDF_HASH — карточка КР подтверждена на cr.minzdrav.gov.ru; нужен полный "
        "PDF и его SHA-256 в clinical_sources/regimen_candidate_specs/<cr_id>.json"
    ),
    "SOURCE_SPEC_MISSING": (
        "SOURCE_SPEC — нет закреплённого источника: создать "
        "clinical_sources/regimen_candidate_specs/<cr_id>.json с expected_pdf_sha256 "
        "и expected_candidates_sha256"
    ),
}


def _cr_key(cr_id: Any) -> str:
    value = str(cr_id or "").strip()
    return "" if value in {"", "—", "-"} else value


def _display_path(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise (never raises)."""
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def load_specs(specs_dir: Path = SPECS_DIR) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    if not specs_dir.is_dir():
        return specs
    for path in sorted(specs_dir.glob("*.json")):
        if path.name == "README.md":
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            specs[path.stem] = {"_unreadable": True, "file": path.name}
            continue
        key = str(raw.get("guideline_id") or path.stem)
        specs[key] = {
            "file": path.name,
            "has_pdf_sha256": bool(raw.get("expected_pdf_sha256")),
            "has_candidates_sha256": bool(raw.get("expected_candidates_sha256")),
            "guideline_title": raw.get("guideline_title"),
            "approval_year": raw.get("approval_year"),
        }
    return specs


def build_report(db_path: Path = DB_PATH, specs_dir: Path = SPECS_DIR) -> dict[str, Any]:
    db = json.loads(db_path.read_text(encoding="utf-8-sig"))
    specs = load_specs(specs_dir)
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()

    for rec in db.get("recommendations", []):
        cr_id = _cr_key(rec.get("cr_id"))
        spec = specs.get(cr_id) if cr_id else None
        status = str(rec.get("source_verification_status") or "UNSET")
        blocked = bool(rec.get("calculation_blocked"))
        status_counts[status] += 1

        if rec.get("calculation_blocked") and not rec.get("calculation_block_reason"):
            reason_gap = True
        else:
            reason_gap = False

        rows.append(
            {
                "disease_id": rec.get("id"),
                "name": rec.get("name"),
                "cr_id": cr_id or None,
                "cr_year": rec.get("cr_year"),
                "source_url": rec.get("source_url"),
                "calculation_blocked": blocked,
                "source_verification_status": status,
                "source_spec": spec,
                "guideline_links": len(rec.get("guideline_links") or []),
                "next_action": NEXT_ACTION.get(status, f"UNKNOWN_STATUS:{status}"),
                "missing_block_reason": reason_gap,
            }
        )

    # Policy invariants — a breach here means the gate stopped being fail-closed.
    breaches = [
        {
            "code": "UNBLOCKED_WITHOUT_VERIFIED_STATUS",
            "disease_id": row["disease_id"],
            "detail": f"расчёт открыт при статусе {row['source_verification_status']}",
        }
        for row in rows
        if not row["calculation_blocked"] and row["source_verification_status"] != "CALCULATOR_BOUND_VERIFIED"
    ]
    breaches += [
        {"code": "BLOCKED_WITHOUT_REASON", "disease_id": row["disease_id"], "detail": "нет calculation_block_reason"}
        for row in rows
        if row["missing_block_reason"]
    ]

    ladder = Counter(row["next_action"].split(" — ")[0] for row in rows)
    return {
        "artifact_type": "CALCULATOR_SOURCE_GATE_REPORT",
        "schema_version": "1.0.0",
        "generated_from": {
            "calculator_db": _display_path(db_path),
            "specs_dir": _display_path(specs_dir),
        },
        "warning": (
            "Диагностика блокировок. Отчёт ничего не разблокирует и не подтверждает "
            "схемы клинически."
        ),
        "totals": {
            "diseases": len(rows),
            "blocked": sum(1 for r in rows if r["calculation_blocked"]),
            "open": sum(1 for r in rows if not r["calculation_blocked"]),
            "specs_available": len(specs),
            "diseases_with_pinned_spec": sum(1 for r in rows if r["source_spec"]),
            "diseases_with_guideline_links": sum(1 for r in rows if r["guideline_links"]),
        },
        "status_counts": dict(sorted(status_counts.items())),
        "remediation_ladder": dict(sorted(ladder.items())),
        "policy_breaches": breaches,
        "rows": sorted(rows, key=lambda row: (row["next_action"], row["disease_id"] or "")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report calculator source-gate blocks and next actions")
    parser.add_argument("--db", default=str(DB_PATH), type=Path)
    parser.add_argument("--specs", default=str(SPECS_DIR), type=Path)
    parser.add_argument("--json", default=None, type=Path, help="write the machine-readable report here")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a fail-closed invariant is breached")
    args = parser.parse_args(argv)

    report = build_report(args.db, args.specs)
    totals = report["totals"]

    print("=== Calculator source gate ===")
    print(f"Нозологий: {totals['diseases']} · расчёт открыт: {totals['open']} · заблокировано: {totals['blocked']}")
    print(f"Закреплённых источников (specs): {totals['specs_available']} · нозологий со spec: {totals['diseases_with_pinned_spec']}")
    print(f"Нозологий со связкой к корпусу КР: {totals['diseases_with_guideline_links']}")
    print("\nСтатусы:")
    for status, count in report["status_counts"].items():
        print(f"  {count:4d}  {status}")
    print("\nЧто делать дальше:")
    for action, count in report["remediation_ladder"].items():
        print(f"  {count:4d}  {action}")

    if report["policy_breaches"]:
        print(f"\n❌ Нарушения fail-closed политики: {len(report['policy_breaches'])}")
        for breach in report["policy_breaches"][:20]:
            print(f"  {breach['code']}: {breach['disease_id']} — {breach['detail']}")
    else:
        print("\n✅ Fail-closed инварианты соблюдены")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"\nОтчёт записан: {args.json}")

    if args.strict and report["policy_breaches"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
