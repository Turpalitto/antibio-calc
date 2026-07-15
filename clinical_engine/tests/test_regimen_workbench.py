"""Regimen Review Workbench tests (read-only, physician-review artifacts).

Uses a throwaway mini-corpus. Proves: correct area matching (ICD + keyword),
mechanical anomaly flags, artifact generation with provenance + source quote,
ledger scaffolding (pending, no auto-approval), and that the corpus is untouched.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.tools import regimen_review_workbench as wb


def _corpus(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    nr = sqlite3.connect(root / "normalized_regimens.sqlite")
    nr.execute("""CREATE TABLE normalized_regimens (
        regimen_id TEXT, guideline_id TEXT, drug_original TEXT, drug_normalized TEXT,
        dose REAL, dose_unit TEXT, route TEXT, frequency REAL,
        duration_min REAL, duration_max REAL, duration_recommended REAL, therapy_line TEXT,
        population TEXT, adult INTEGER, child INTEGER, pregnancy TEXT, renal_adjustment TEXT,
        validation_verdict TEXT, validation_issues TEXT, overall_confidence REAL,
        source_pdf TEXT, source_page TEXT, source_quote TEXT, mkb TEXT, diagnosis TEXT)""")
    # a clean cystitis regimen (PASS) and an anomalous one (REJECT, no dose)
    nr.execute("""INSERT INTO normalized_regimens VALUES
        ('5576','1127','Фосфомицин','Фосфомицин',3.0,'g','oral',1.0,1.0,1.0,NULL,'first',
         'adult',1,0,NULL,NULL,'PASS','',0.92,'cystitis.pdf','5',
         'Фосфомицин 3 г однократно','N30.0','Острый цистит')""")
    nr.execute("""INSERT INTO normalized_regimens VALUES
        ('5577','1127','фуразидин','фуразидин',NULL,'','unknown',NULL,NULL,NULL,NULL,'first',
         'adult',1,0,NULL,NULL,'REJECT','DRUG_UNKNOWN',0.46,'cystitis.pdf','5',
         'Фуразидин ... ','N30.0','Острый цистит')""")
    nr.execute("""INSERT INTO normalized_regimens VALUES
        ('9001','2101','тобрамицин','тобрамицин',NULL,'','unknown',NULL,NULL,NULL,NULL,'first',
         'adult',1,0,NULL,NULL,'REJECT','DRUG_UNKNOWN',0.31,'dacryo.pdf','16',
         'антибактериальная терапия при дакриоцистите','H04.3','Дакриоцистит')""")
    nr.execute("""INSERT INTO normalized_regimens VALUES
        ('5578','9999','амоксициллин','амоксициллин',500.0,'mg','oral',3.0,7.0,7.0,NULL,'first',
         'adult',1,0,NULL,NULL,'PASS','',0.91,'keyword.pdf','9',
         'Антибактериальная терапия при цистите','Z99','Бактериальный цистит эпизод')""")
    nr.commit(); nr.close()

    md = sqlite3.connect(root / "metadata.sqlite")
    md.execute("""CREATE TABLE antibiotic_regimens (id INTEGER, clinrec_id INTEGER,
        diagnosis TEXT, clinrec_name TEXT, guideline_name TEXT, mkb TEXT,
        pdf_sha256 TEXT, page_number TEXT, pdf_file TEXT)""")
    for rid in (5576, 5577):
        md.execute("INSERT INTO antibiotic_regimens VALUES (?,1127,'Острый цистит','Цистит у женщин',"
                    "'Цистит у женщин','N30.0','abc123def456',?, 'cystitis.pdf')", (rid, "5"))
    md.execute("INSERT INTO antibiotic_regimens VALUES (9001,2101,'Дакриоцистит','Дакриоцистит',"
               "'Врожденная патология слёзоотводящей системы у детей','H04.3','deadbeef',"
               "'16','dacryo.pdf')")
    md.execute("INSERT INTO antibiotic_regimens VALUES (5578,9999,'Бактериальный цистит эпизод','Цистит',"
               "'Цистит','Z99','feedbeef','9','keyword.pdf')")
    md.commit(); md.close()


def _loc(root: Path) -> CorpusLocator:
    return CorpusLocator(root)


def test_area_matching_by_icd_and_keyword(tmp_path):
    _corpus(tmp_path / "c")
    md = _loc(tmp_path / "c").open_metadata()
    try:
        area = wb._AREAS_BY_ID["acute_cystitis"]
        assert wb._candidate_ids(md, area) == {"5576", "5577", "5578", "9001"}
    finally:
        md.close()


def test_anomaly_flags_mechanical(tmp_path):
    _corpus(tmp_path / "c")
    data = wb.collect(_loc(tmp_path / "c"), ["acute_cystitis"])
    rows = {r["regimen_id"]: r for r in data["rows"]}
    assert rows["5576"]["anomalies"] == []            # clean PASS regimen
    a = rows["5577"]["anomalies"]
    assert "DOSE_MISSING" in a and "ROUTE_UNKNOWN" in a and "FREQ_MISSING" in a
    assert "VERDICT_REJECT" in a and "DRUG_UNKNOWN" in a


def test_matching_metadata_and_negative_keywords(tmp_path):
    _corpus(tmp_path / "c")
    data = wb.collect(_loc(tmp_path / "c"), ["acute_cystitis"])
    rows = {r["regimen_id"]: r for r in data["rows"]}
    assert rows["5576"]["confidence"] == 95
    assert rows["5576"]["match_reason"] == "ICD N30"
    assert rows["5576"]["needs_manual_review"] is False
    assert data["excluded_ids"] == ["9001"]
    assert data["excluded_false_positives"] == 1


def test_rows_sorted_by_area_priority_diagnosis(tmp_path):
    _corpus(tmp_path / "c")
    data = wb.collect(_loc(tmp_path / "c"), ["acute_cystitis"])
    rows = data["rows"]
    assert [(r["regimen_id"], r["priority"], r["confidence"], r["diagnosis"]) for r in rows] == [
        ("5576", 2, 95, "Острый цистит"),
        ("5577", 2, 95, "Острый цистит"),
        ("5578", 5, 60, "Бактериальный цистит эпизод"),
    ]


def test_target_areas_loaded_from_external_config(tmp_path):
    cfg = tmp_path / "areas.json"
    cfg.write_text(json.dumps({"areas": [{
        "area_id": "test_area",
        "label": "Test Area",
        "icd_prefixes": ["A01"],
        "diagnosis_names": ["Test diagnosis"],
        "keywords": ["test"],
        "exclude": ["not test"],
        "guideline_ids": ["42"]
    }]}, ensure_ascii=False), encoding="utf-8")
    areas = wb._load_target_areas(cfg)
    assert areas[0] == wb.TargetArea(
        "test_area", "Test Area", ("A01",), ("Test diagnosis",), ("test",), ("not test",), ("42",)
    )


def test_build_artifacts_and_provenance(tmp_path):
    _corpus(tmp_path / "c")
    r = wb.build(["acute_cystitis"], ledger_path=str(tmp_path / "led.json"),
                 out_md=str(tmp_path / "wb.md"), out_csv=str(tmp_path / "wb.csv"),
                 locator=_loc(tmp_path / "c"))
    assert r["queued"] == 3 and r["with_anomalies"] == 1
    md = (tmp_path / "wb.md").read_text(encoding="utf-8")
    # side-by-side quote + provenance present
    assert "Guideline quote" in md and "Фосфомицин 3 г однократно" in md
    assert "guideline_id `1127`" in md and "abc123def456"[:16] in md
    assert "READ-ONLY" in md
    # CSV has physician decision columns
    csv_txt = (tmp_path / "wb.csv").read_text(encoding="utf-8-sig")
    assert "needs_manual_review" in csv_txt and "match_reason" in csv_txt


def test_build_does_not_write_ledger_by_default(tmp_path):
    _corpus(tmp_path / "c")
    led = tmp_path / "led.json"
    wb.build(["acute_cystitis"], ledger_path=str(led), out_md=str(tmp_path / "m.md"),
             out_csv=str(tmp_path / "m.csv"), locator=_loc(tmp_path / "c"))
    assert not led.exists()


def test_update_ledger_opt_in_is_pending_no_autoapproval(tmp_path):
    _corpus(tmp_path / "c")
    led = tmp_path / "led.json"
    wb.build(["acute_cystitis"], ledger_path=str(led), out_md=str(tmp_path / "m.md"),
             out_csv=str(tmp_path / "m.csv"), update_ledger=True, locator=_loc(tmp_path / "c"))
    doc = json.loads(led.read_text(encoding="utf-8"))
    assert {d["regimen_id"] for d in doc["decisions"]} == {"5576", "5577", "5578"}
    assert all(d["decision"] == "pending_review" and d["decided_by"] == "" for d in doc["decisions"])


def test_corpus_untouched(tmp_path):
    _corpus(tmp_path / "c")
    corpus = tmp_path / "c"
    before = {p.name: p.stat().st_mtime for p in corpus.iterdir()}
    wb.build(["acute_cystitis"], ledger_path=str(tmp_path / "led.json"),
             out_md=str(tmp_path / "m.md"), out_csv=str(tmp_path / "m.csv"), locator=_loc(corpus))
    after = {p.name: p.stat().st_mtime for p in corpus.iterdir()}
    assert before == after


def test_real_corpus_smoke(tmp_path):
    import pytest
    loc = CorpusLocator()
    if not loc.available():
        pytest.skip("external corpus not present")
    r = wb.build(["acute_cystitis"], ledger_path=str(tmp_path / "led.json"),
                  out_md=str(tmp_path / "wb.md"), out_csv=str(tmp_path / "wb.csv"), locator=loc)
    assert r["queued"] > 0
    assert (tmp_path / "wb.md").read_text(encoding="utf-8").count("regimen_id") > 0
