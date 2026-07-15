"""Phase 15 — Real data pilot.

Selects a small read-only QA set from assembled_regimens.sqlite and runs each
case through the parser + calculator, producing a report. Read-only: opens the
source DB with mode=ro and never writes to it. Writes only to
dose_verification_sandbox/data/pilot_report.json and .md.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from dataclasses import asdict

from .parser import parse_dose_expression
from .calculator import calculate
from .verify import build_verification_result

DB = Path(__file__).resolve().parents[1] / "assembled_regimens.sqlite"
DATA_DIR = Path(__file__).parent / "data"

DEFAULT_WEIGHTS = {"child": 18.0, "adult": 70.0}


def _readonly_connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)


def _select_cases(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    cases: list[dict] = []

    def q(sql: str, limit: int) -> list[dict]:
        cur.execute(sql + f" LIMIT {limit}")
        return [dict(r) for r in cur.fetchall()]

    cases += q("""SELECT * FROM assembled_regimens
                  WHERE unit='mg/kg' AND age_group='child' AND frequency IS NOT NULL
                  ORDER BY regimen_id""", 5)
    cases += q("""SELECT * FROM assembled_regimens
                  WHERE unit='mg' AND age_group='adult' AND frequency IS NOT NULL
                  ORDER BY regimen_id""", 5)
    # No dose-range columns exist in this schema at all (audit §4) — 0 real
    # dose-range cases available; recorded explicitly rather than padded.
    # No max-dose columns exist at all (audit §7) — 0 real max-dose cases available.
    # No formulation/concentration columns exist at all (audit §10) — 0 real
    # formulation-conversion cases available.
    cases += q("""SELECT * FROM assembled_regimens WHERE unit LIKE '%;%'
                  ORDER BY regimen_id""", 2)
    return cases


def run_pilot() -> Path:
    conn = _readonly_connect(DB)
    try:
        rows = _select_cases(conn)
    finally:
        conn.close()

    results = []
    for row in rows:
        weight = DEFAULT_WEIGHTS.get(row.get("age_group") or "adult", 70.0)
        expr = parse_dose_expression(row.get("dose"), row.get("unit"), row.get("frequency"))
        trace = calculate(expr, weight_kg=weight)
        verdict = build_verification_result(row, expr, trace)
        results.append({
            "regimen_id": row.get("regimen_id"),
            "version": row.get("version"),
            "diagnosis_mkb": row.get("icd_mkb"),
            "diagnosis": row.get("diagnosis"),
            "antibiotic": row.get("antibiotic"),
            "age_group": row.get("age_group"),
            "assumed_weight_kg": weight,
            "source_formula": expr.source_expression,
            "source_pdf": row.get("source_pdf"),
            "source_page": row.get("source_page"),
            "source_quote": row.get("source_quote"),
            "status": row.get("status"),
            "review_status": row.get("review_status"),
            "validation_verdict": row.get("validation_verdict"),
            "calculation_status": trace.calculation_status,
            "final_min_daily_dose": trace.final_min_daily_dose,
            "final_max_daily_dose": trace.final_max_daily_dose,
            "final_min_single_dose": trace.final_min_single_dose,
            "final_max_single_dose": trace.final_max_single_dose,
            "warnings": trace.warnings,
            "verdict": asdict(verdict),
        })

    dose_range_cases = 0
    max_dose_cases = 0
    formulation_cases = 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "meta": {
            "label": "QA / RESEARCH ONLY — NOT CLINICALLY APPROVED — DO NOT USE FOR PATIENT CARE",
            "source_db": str(DB.name),
            "note": (
                "assembled_regimens.sqlite has no dose-range, max-dose, or formulation/"
                "concentration columns — those pilot categories from the P5.6 spec have "
                "zero real cases available and are reported as 0, not padded with synthetic data."
            ),
            "counts": {
                "pediatric_weight_based": sum(1 for r in results if r["age_group"] == "child"),
                "adult_fixed_dose": sum(1 for r in results if r["age_group"] == "adult"),
                "dose_range": dose_range_cases,
                "max_dose": max_dose_cases,
                "formulation_conversion": formulation_cases,
                "blocked_unparsed": sum(1 for r in results if r["calculation_status"] == "BLOCKED"),
            },
        },
        "cases": results,
    }

    out_json = DATA_DIR / "pilot_report.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Dose Verification Sandbox — Real Data Pilot (Phase 15)",
        "",
        "QA / RESEARCH ONLY — NOT CLINICALLY APPROVED — DO NOT USE FOR PATIENT CARE",
        "",
        f"Source: `{DB.name}` (assembled_regimens table), opened read-only.",
        "",
        "No dose-range, max-dose, or formulation-conversion real cases exist in this table "
        "(no such columns in the schema) — counted as 0 below rather than fabricated.",
        "",
        "| regimen_id | mkb | antibiotic | source | calc_status | final daily dose | verdict.arithmetic | status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['regimen_id']} | {r['diagnosis_mkb']} | {r['antibiotic']} | "
            f"{r['source_formula']} | {r['calculation_status']} | "
            f"{r['final_max_daily_dose']} | {r['verdict']['arithmetic']} | {r['status']} |"
        )
    out_md = DATA_DIR / "pilot_report.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")
    return out_json


if __name__ == "__main__":
    p = run_pilot()
    print(f"Pilot report written to {p}")
