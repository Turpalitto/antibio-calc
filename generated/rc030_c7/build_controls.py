"""RC-030 C7 Part IV Phase 7 -- synthetic control records for interface
testing only. Not genuine owner task IDs, all test_event=true, never
placed inside governed precision input.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "generated" / "rc030_c7" / "synthetic_controls.json"


def _hash(rid: str) -> str:
    return hashlib.sha256(f"SYNTHETIC_CONTROL::{rid}".encode("utf-8")).hexdigest()


def main() -> None:
    controls = [
        {
            "regimen_id": "TEST-CONTROL-CONFIRMING", "regimen_version": 1,
            "evidence_hash": _hash("CONFIRMING"), "test_event": True,
            "antibiotic": "Тестамициллин", "diagnosis": "Synthetic test diagnosis",
            "route": "oral", "frequency": 2, "duration_recommended": 7,
            "dose": 20.0, "unit": "mg/kg/day",
            "source_pdf": "SYNTHETIC_TEST_ONLY.pdf", "source_page": "1",
            "source_quote": "тестамициллин** 20-40 мг/кг/сут внутрь",
            "control_type": "CONFIRMING", "pdf_hash": _hash("PDF_CONFIRMING"),
        },
        {
            "regimen_id": "TEST-CONTROL-WRONG-ANCHOR", "regimen_version": 1,
            "evidence_hash": _hash("WRONG_ANCHOR"), "test_event": True,
            "antibiotic": "Тестамициллин", "diagnosis": "Synthetic test diagnosis",
            "route": "oral", "frequency": 1, "duration_recommended": 5,
            "dose": 500.0, "unit": "mg",
            "source_pdf": "SYNTHETIC_TEST_ONLY.pdf", "source_page": "1",
            "source_quote": "тестомицин** 10-20 мг/кг; тестамициллин** 500 мг однократно",
            "control_type": "WRONG_ANCHOR", "pdf_hash": _hash("PDF_WRONG_ANCHOR"),
        },
        {
            "regimen_id": "TEST-CONTROL-AMBIGUOUS", "regimen_version": 1,
            "evidence_hash": _hash("AMBIGUOUS"), "test_event": True,
            "antibiotic": "Тестамициллин", "diagnosis": "Synthetic test diagnosis",
            "route": "iv", "frequency": 3, "duration_recommended": 10,
            "dose": 30.0, "unit": "mg/kg",
            "source_pdf": "SYNTHETIC_TEST_ONLY.pdf", "source_page": "1",
            "source_quote": "тестамициллин** 20-40 мг/кг или 30-60 мг/кг в зависимости от тяжести",
            "control_type": "AMBIGUOUS", "pdf_hash": _hash("PDF_AMBIGUOUS"),
        },
        {
            "regimen_id": "TEST-CONTROL-SOURCE-BLOCKED", "regimen_version": 1,
            "evidence_hash": _hash("SOURCE_BLOCKED"), "test_event": True,
            "antibiotic": "Тестамициллин", "diagnosis": "Synthetic test diagnosis",
            "route": "iv", "frequency": 1, "duration_recommended": 3,
            "dose": 15.0, "unit": "mg/kg",
            "source_pdf": "SYNTHETIC_TEST_ONLY.pdf", "source_page": "999",
            "source_quote": "[synthetic quote deliberately not present in any real PDF]",
            "control_type": "SOURCE_BLOCKED", "pdf_hash": _hash("PDF_SOURCE_BLOCKED"),
        },
    ]
    for c in controls:
        c["calculation_eligibility"] = "BLOCKED"
        c["clinically_approved"] = False
        c["authoritative_migration_allowed"] = False

    out = {"schema_version": 1, "purpose": "interface testing only -- never governed precision input",
           "count": len(controls), "records": controls}
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(controls)} synthetic controls written to {OUT_PATH}")


if __name__ == "__main__":
    main()
