"""Clinical Guideline Verification tool tests.

Uses a throwaway corpus and injected page text provider. Verifies read-only,
field-by-field comparison, JSON/Markdown/CSV artifacts, and no physician
approval/rejection semantics.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.tools import verify_regimen_against_guideline as vg


def _corpus(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    nr = sqlite3.connect(root / "normalized_regimens.sqlite")
    nr.execute("""CREATE TABLE normalized_regimens (
        regimen_id TEXT, guideline_id TEXT, drug_normalized TEXT, dose REAL,
        dose_unit TEXT, route TEXT, frequency REAL, duration_min REAL,
        duration_max REAL, duration_recommended REAL, therapy_line TEXT,
        adult INTEGER, child INTEGER, pregnancy TEXT, renal_adjustment TEXT,
        source_pdf TEXT, source_page TEXT, source_quote TEXT, review_status TEXT,
        reviewed_by TEXT, review_date TEXT, approved INTEGER)""")
    nr.execute("""INSERT INTO normalized_regimens VALUES
        ('r_match','g1','Амоксициллин',500.0,'mg','oral',3.0,7.0,7.0,7.0,'first',
         1,0,NULL,NULL,'guide.pdf','5','Амоксициллин 500 мг внутрь 3 раза в день 7 дней','pending_review','','',0)""")
    nr.execute("""INSERT INTO normalized_regimens VALUES
        ('r_mismatch','g1','Амоксициллин',500.0,'mg','oral',3.0,5.0,5.0,5.0,'first',
         1,0,NULL,NULL,'guide.pdf','5','Амоксициллин 500 мг внутрь 3 раза в день 7 дней','pending_review','','',0)""")
    nr.commit(); nr.close()

    md = sqlite3.connect(root / "metadata.sqlite")
    md.execute("""CREATE TABLE antibiotic_regimens (
        id TEXT, clinrec_id TEXT, pdf_file TEXT, pdf_sha256 TEXT, page_number TEXT,
        source_quote TEXT, section_name TEXT, diagnosis TEXT)""")
    for rid in ("r_match", "r_mismatch"):
        md.execute("INSERT INTO antibiotic_regimens VALUES (?, 'g1', 'guide.pdf', 'sha', '5', "
                   "'Амоксициллин 500 мг внутрь 3 раза в день 7 дней', "
                   "'Антибактериальная терапия', 'Острый синусит')", (rid,))
    md.execute("CREATE TABLE clinrecs (id TEXT, code TEXT)")
    md.execute("INSERT INTO clinrecs VALUES ('g1', 'KR-1')")
    md.commit(); md.close()
    (root / "downloads_active").mkdir()
    (root / "downloads_active" / "guide.pdf").write_bytes(b"fake pdf bytes")


def _pages(_: str) -> list[str]:
    return ["", "", "", "", "Острый синусит. Амоксициллин 500 мг внутрь 3 раза в день 7 дней."]


def test_verifies_matching_and_mismatching_regimens(tmp_path):
    _corpus(tmp_path / "c")
    reports = vg.verify_regimens(["r_match", "r_mismatch"], locator=CorpusLocator(tmp_path / "c"),
                                 page_text_provider=_pages, verify_pdf_hash=False)
    by_id = {r["regimen_id"]: r for r in reports}
    assert by_id["r_match"]["recommendation_status"] == "LIKELY_MATCH"
    assert by_id["r_match"]["quality_score"] == 100
    assert by_id["r_match"]["field_comparisons"]["duration"]["status"] == "MATCH"
    assert by_id["r_mismatch"]["recommendation_status"] == "LIKELY_MISMATCH"
    assert by_id["r_mismatch"]["field_comparisons"]["duration"]["status"] == "MISMATCH"
    assert by_id["r_mismatch"]["field_comparisons"]["duration"]["guideline_value"] == "7.0"
    assert "approve" not in json.dumps(reports, ensure_ascii=False).lower()
    assert "reject" not in json.dumps(reports, ensure_ascii=False).lower()


def test_from_workbench_csv_and_artifacts_are_read_only(tmp_path):
    _corpus(tmp_path / "c")
    corpus = tmp_path / "c"
    before = {p.name: p.stat().st_mtime for p in corpus.iterdir()}
    wb = tmp_path / "workbench.csv"
    wb.write_text("regimen_id\nr_match\nr_mismatch\n", encoding="utf-8")
    out_json, out_md, out_csv = tmp_path / "v.json", tmp_path / "v.md", tmp_path / "v.csv"
    result = vg.build(regimen_ids=[], from_workbench_csv=str(wb), out_json=str(out_json),
                      out_md=str(out_md), out_csv=str(out_csv), locator=CorpusLocator(corpus),
                      page_text_provider=_pages, verify_pdf_hash=False)
    after = {p.name: p.stat().st_mtime for p in corpus.iterdir()}
    assert before == after
    assert result["total"] == 2
    assert json.loads(out_json.read_text(encoding="utf-8"))[0]["regimen_id"] == "r_match"
    assert "Field-by-field comparison" in out_md.read_text(encoding="utf-8")
    assert "recommendation_status" in out_csv.read_text(encoding="utf-8-sig")


def test_unverifiable_when_source_block_missing(tmp_path):
    _corpus(tmp_path / "c")
    reports = vg.verify_regimens(["r_match"], locator=CorpusLocator(tmp_path / "c"),
                                 page_text_provider=lambda _: ["no relevant text"], verify_pdf_hash=False)
    assert reports[0]["recommendation_status"] == "UNVERIFIABLE"
    assert reports[0]["field_comparisons"]["drug"]["status"] == "UNVERIFIABLE"
