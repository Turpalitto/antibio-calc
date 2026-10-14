"""`db/db_diff.py` — clinical diff between two DB builds (audit 2026-10-14, I-6)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "db" / "db_diff.py"


def _load():
    spec = importlib.util.spec_from_file_location("antibio_db_diff", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


db_diff = _load()


def _db() -> dict:
    return {
        "meta": {"version": "x"},
        "drugs_reference": {
            "_note": "ignored",
            "amoxicillin": {"forms": [{"form_type": "tablet", "concentration": "500 мг"}], "age_restriction_min": None},
        },
        "recommendations": [
            {
                "id": "cap_child", "name": "ВП дети", "cr_id": "714_2", "cr_year": 2022,
                "calculation_blocked": False, "source_verification_status": "CR_REFERENCE_CALCULATION",
                "age_groups": ["child"], "mkb10": ["J18"],
                "scenarios": [{
                    "id": "out", "lines": [{
                        "line_number": 1, "drugs": [{
                            "drug_ref": "amoxicillin", "route": ["per_os"],
                            "regimens": [
                                {"age_group": "child", "dose_mg_kg_day": 90, "freq_per_day": 2, "max_daily_mg": 3000},
                                {"age_group": "child", "dose_mg_kg_day": 90, "freq_per_day": 3, "max_daily_mg": 3000},
                            ],
                        }],
                    }],
                }],
            },
            {"id": "aom_child", "name": "ОСО", "cr_id": "—", "scenarios": []},
        ],
    }


def test_identical_databases_report_no_change() -> None:
    report = db_diff.diff_db(_db(), _db())
    assert report["changed"] is False
    assert report["summary"]["records_changed"] == 0
    md = db_diff.render_markdown(report, old_label="a", new_label="b")
    assert "no clinical data changes" in md


def test_regimen_field_changes_are_reported_per_age_group_and_duplicate_groups_are_kept_apart() -> None:
    old, new = _db(), _db()
    # the SECOND child regimen (3×/day) gets a lower ceiling; the first is untouched
    new["recommendations"][0]["scenarios"][0]["lines"][0]["drugs"][0]["regimens"][1]["max_daily_mg"] = 2000
    report = db_diff.diff_db(old, new)
    assert report["changed"] is True
    entry = report["records_changed"][0]
    assert entry["id"] == "cap_child"
    assert entry["regimens"] == [{
        "drug": "out / line 1 / amoxicillin", "age_group": "child#2", "change": "changed",
        "fields": {"max_daily_mg": {"old": 3000, "new": 2000}},
    }]
    md = db_diff.render_markdown(report, old_label="a", new_label="b")
    assert "regimen out / line 1 / amoxicillin [child#2]: max_daily_mg 3000 → 2000" in md


def test_blocking_status_and_explicit_flag_are_distinguished() -> None:
    old, new = _db(), _db()
    new["recommendations"][0]["calculation_blocked"] = True          # false → true
    new["recommendations"][0]["source_verification_status"] = "SOURCE_BASIS_MISSING"
    new["recommendations"][1]["calculation_blocked"] = False         # missing → false
    report = db_diff.diff_db(old, new)
    s = report["summary"]
    assert s["blocked_now"] == ["cap_child"]
    assert s["unblocked_now"] == []
    assert s["block_flag_made_explicit"] == ["aom_child"]
    assert s["old_blocked"] == 0 and s["new_blocked"] == 1
    # true → false IS an unblock
    report2 = db_diff.diff_db(new, old)
    assert report2["summary"]["unblocked_now"] == ["cap_child"]
    md = db_diff.render_markdown(report2, old_label="a", new_label="b")
    assert "**UNBLOCKED (owner attention):** cap_child" in md


def test_added_removed_records_drugs_routes_and_reference_keys() -> None:
    old, new = _db(), _db()
    new["recommendations"].append({"id": "new_rec", "name": "n", "scenarios": []})
    del new["recommendations"][1]                                    # aom_child removed
    drug = new["recommendations"][0]["scenarios"][0]["lines"][0]["drugs"]
    drug[0]["route"] = ["per_os", "iv"]
    drug.append({"drug_ref": "azithromycin", "route": ["per_os"], "regimens": []})
    new["drugs_reference"]["amoxicillin"]["age_restriction_min"] = "1 мес"
    new["drugs_reference"]["cefixime"] = {"forms": []}
    report = db_diff.diff_db(old, new)
    assert report["records_added"] == ["new_rec"] and report["records_removed"] == ["aom_child"]
    entry = report["records_changed"][0]
    assert entry["drugs_added"] == ["out / line 1 / azithromycin"]
    assert entry["routes_changed"] == [{"drug": "out / line 1 / amoxicillin", "old": ["per_os"], "new": ["per_os", "iv"]}]
    assert report["drugs_reference_changed"] == [
        {"drug": "amoxicillin", "change": "changed", "keys": ["age_restriction_min"]},
        {"drug": "cefixime", "change": "added"},
    ]


def test_cli_with_two_files_and_fail_on_change(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(_db(), ensure_ascii=False), encoding="utf-8")
    changed = _db()
    changed["recommendations"][0]["cr_year"] = 2024
    b.write_text("\ufeff" + json.dumps(changed, ensure_ascii=False), encoding="utf-8")   # BOM tolerated
    assert db_diff.main([str(a), str(a), "--fail-on-change"]) == 0
    assert db_diff.main([str(a), str(b), "--fail-on-change"]) == 3
    out = capsys.readouterr().out
    assert "cr_year: 2022 → 2024" in out
    assert db_diff.main([str(a), str(b), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["records_changed"][0]["fields"]["cr_year"] == {"old": 2022, "new": 2024}


def test_cli_rejects_a_non_database_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert db_diff.main([str(bad), str(bad)]) == 2


def test_git_mode_compares_the_shipped_db_with_the_working_tree() -> None:
    report = db_diff.diff_db(db_diff.load_db_git("HEAD"), db_diff.load_db_file(db_diff.DB_PATH))
    assert report["summary"]["new_records"] == 120
