"""Tests for db/source_gate_report.py — the "why is this blocked?" worklist.

The calculator fail-closes 119 of 120 nozologies. That is correct behaviour, but
it is only defensible if the reason and the remediation step are explicit. These
tests pin the report's invariants, including the two fail-closed checks that must
never regress.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from db.source_gate_report import NEXT_ACTION, build_report, load_specs, main


def _write(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _db(records):
    return {"recommendations": records}


@pytest.fixture()
def fixture(tmp_path: Path):
    db_path = _write(
        tmp_path / "antibio_db.json",
        _db(
            [
                {
                    "id": "verified",
                    "name": "Проверенная",
                    "cr_id": "9_3",
                    "cr_year": 2024,
                    "source_url": "https://cr.minzdrav.gov.ru/view-cr/9_3",
                    "calculation_blocked": False,
                    "source_verification_status": "CALCULATOR_BOUND_VERIFIED",
                    "guideline_links": [{"guideline_id": "1"}],
                },
                {
                    "id": "spec_only",
                    "name": "Со spec, без привязки",
                    "cr_id": "306_3",
                    "calculation_blocked": True,
                    "source_verification_status": "SOURCE_SPEC_PENDING_CALCULATOR_BINDING",
                    "calculation_block_reason": "закрыто",
                },
                {
                    "id": "no_spec",
                    "name": "Без источника",
                    "cr_id": "—",
                    "calculation_blocked": True,
                    "source_verification_status": "SOURCE_SPEC_MISSING",
                    "calculation_block_reason": "закрыто",
                },
            ]
        ),
    )
    specs_dir = tmp_path / "specs"
    _write(
        specs_dir / "9_3.json",
        {
            "guideline_id": "9_3",
            "guideline_title": "Острый пиелонефрит",
            "approval_year": 2024,
            "expected_pdf_sha256": "sha256:aaa",
            "expected_candidates_sha256": "sha256:bbb",
        },
    )
    _write(
        specs_dir / "306_3.json",
        {
            "guideline_id": "306_3",
            "guideline_title": "Острый тонзиллит и фарингит",
            "approval_year": 2024,
            "expected_pdf_sha256": "sha256:ccc",
            "expected_candidates_sha256": None,
        },
    )
    return db_path, specs_dir



def test_specs_are_loaded_and_hashed_flags_recorded(fixture):
    _db_path, specs_dir = fixture
    specs = load_specs(specs_dir)
    assert specs["9_3"]["has_pdf_sha256"] is True
    assert specs["9_3"]["has_candidates_sha256"] is True
    assert specs["306_3"]["has_candidates_sha256"] is False


def test_load_specs_tolerates_a_missing_directory(tmp_path):
    assert load_specs(tmp_path / "absent") == {}


def test_report_totals_and_ladder(fixture):
    db_path, specs_dir = fixture
    report = build_report(db_path, specs_dir)

    assert report["totals"]["diseases"] == 3
    assert report["totals"]["open"] == 1
    assert report["totals"]["blocked"] == 2
    assert report["totals"]["specs_available"] == 2
    assert report["totals"]["diseases_with_pinned_spec"] == 2
    assert report["totals"]["diseases_with_guideline_links"] == 1

    assert report["status_counts"] == {
        "CALCULATOR_BOUND_VERIFIED": 1,
        "SOURCE_SPEC_MISSING": 1,
        "SOURCE_SPEC_PENDING_CALCULATOR_BINDING": 1,
    }
    assert report["remediation_ladder"] == {"NONE": 1, "SOURCE_SPEC": 1, "SPEC_PINNED": 1}
    assert report["policy_breaches"] == []


def test_every_status_has_a_next_action(fixture):
    db_path, specs_dir = fixture
    report = build_report(db_path, specs_dir)
    for row in report["rows"]:
        assert not row["next_action"].startswith("UNKNOWN_STATUS"), row
    assert set(NEXT_ACTION) >= {
        "CALCULATOR_BOUND_VERIFIED",
        "SOURCE_SPEC_MISSING",
        "SOURCE_SPEC_PENDING_CALCULATOR_BINDING",
        "CURRENT_WEB_CONFIRMED_PDF_PENDING",
        "EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW",
    }


def test_open_calculation_without_verified_status_is_a_policy_breach(tmp_path):
    db_path = _write(
        tmp_path / "antibio_db.json",
        _db(
            [
                {
                    "id": "sneaky",
                    "name": "Открыто без верификации",
                    "cr_id": "1_1",
                    "calculation_blocked": False,
                    "source_verification_status": "SOURCE_SPEC_MISSING",
                }
            ]
        ),
    )
    report = build_report(db_path, tmp_path / "no_specs")
    codes = {breach["code"] for breach in report["policy_breaches"]}
    assert "UNBLOCKED_WITHOUT_VERIFIED_STATUS" in codes
    assert main(["--db", str(db_path), "--specs", str(tmp_path / "no_specs"), "--strict"]) == 1


def test_blocked_without_reason_is_reported(tmp_path):
    db_path = _write(
        tmp_path / "antibio_db.json",
        _db(
            [
                {
                    "id": "silent",
                    "name": "Закрыто без причины",
                    "cr_id": "1_1",
                    "calculation_blocked": True,
                    "source_verification_status": "SOURCE_SPEC_MISSING",
                }
            ]
        ),
    )
    report = build_report(db_path, tmp_path / "no_specs")
    assert "BLOCKED_WITHOUT_REASON" in {b["code"] for b in report["policy_breaches"]}


def test_cli_writes_json_and_passes_without_strict_breaches(fixture, tmp_path, capsys):
    db_path, specs_dir = fixture
    out = tmp_path / "report.json"
    assert main(["--db", str(db_path), "--specs", str(specs_dir), "--json", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["artifact_type"] == "CALCULATOR_SOURCE_GATE_REPORT"
    assert written["totals"]["diseases"] == 3
    assert "ничего не разблокирует" in written["warning"]
    assert "расчёт открыт: 1" in capsys.readouterr().out


def test_report_over_the_real_database_is_consistent():
    """The shipped DB must satisfy the fail-closed invariants."""
    report = build_report()
    assert report["totals"]["diseases"] == len(report["rows"])
    assert report["totals"]["blocked"] + report["totals"]["open"] == report["totals"]["diseases"]
    assert report["policy_breaches"] == []
    # Every blocked nozology must carry a human-readable reason.
    for row in report["rows"]:
        if row["calculation_blocked"]:
            assert not row["missing_block_reason"], row["disease_id"]
