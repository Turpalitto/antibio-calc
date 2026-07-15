import sqlite3
from pathlib import Path

import pytest

from database import init_regimens_table, save_regimens, save_review_required, load_validated_regimens


@pytest.fixture
def db_conn(tmp_path):
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS clinrecs (id INTEGER PRIMARY KEY, name TEXT, code_version TEXT UNIQUE)")
    conn.execute("INSERT INTO clinrecs VALUES (2199, 'Тест', '123_6')")
    init_regimens_table(conn)
    conn.commit()
    yield conn
    conn.close()


def test_init_regimens_table(db_conn):
    cursor = db_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='antibiotic_regimens'")
    assert cursor.fetchone() is not None


def test_save_regimens(db_conn, sample_regimen):
    regimen = {**sample_regimen, "clinrec_id": 2199, "validated": 1, "validation_confidence": 0.92}
    save_regimens(db_conn, [regimen])
    cursor = db_conn.execute("SELECT COUNT(*) FROM antibiotic_regimens")
    assert cursor.fetchone()[0] == 1


def test_save_regimens_stores_all_fields(db_conn, sample_regimen):
    regimen = {**sample_regimen, "clinrec_id": 2199, "validated": 1, "validation_confidence": 0.92}
    save_regimens(db_conn, [regimen])
    cursor = db_conn.execute("SELECT antibiotic, antibiotic_normalized, atc_code, dose, dose_confidence, source_quote FROM antibiotic_regimens")
    row = cursor.fetchone()
    assert row[0] == "амоксициллин"
    assert row[1] == "amoxicillin"
    assert row[2] == "J01CA04"
    assert row[3] == "500-1000"
    assert row[4] == 0.96
    assert "Амоксициллин" in row[5]


def test_load_validated_regimens(db_conn, sample_regimen):
    regimen = {**sample_regimen, "clinrec_id": 2199, "validated": 1, "validation_confidence": 0.92}
    save_regimens(db_conn, [regimen])
    loaded = load_validated_regimens(db_conn)
    assert len(loaded) == 1
    assert loaded[0]["antibiotic"] == "амоксициллин"
    assert loaded[0]["validated"] == 1


def test_save_review_required(tmp_path):
    review_path = tmp_path / "review_required.json"
    items = [
        {
            "clinrec_id": 2199,
            "guideline_name": "Тест",
            "code_version": "123_6",
            "pdf_file": "test.pdf",
            "abx_level": "C",
            "reason": "level_c_keyword_only",
            "confidence": 0.3,
            "page_number": "1",
            "section_name": "",
            "extracted_data": {},
            "expected_fix": "Review manually",
            "validation_issues": [],
        }
    ]
    save_review_required(items, review_path)
    import json
    data = json.loads(review_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["reason"] == "level_c_keyword_only"
