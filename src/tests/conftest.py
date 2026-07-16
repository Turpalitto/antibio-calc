import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def sample_pdf_text():
    return """
    РАЗДЕЛ 3. ЛЕЧЕНИЕ

    3.1 Антибактериальная терапия

    Препаратом выбора является амоксициллин 500-1000 мг 3 раза в день внутрь
    в течение 7-10 дней.

    Альтернативный препарат: азитромицин 500 мг 1 раз в день внутрь 3 дня.

    При тяжелом течении: цефтриаксон 1 г внутривенно 2 раза в день 7-14 дней.

    3.2 Профилактика

    Периоперационная профилактика: цефазолин 2 г внутривенно за 30 мин до операции.
    """


@pytest.fixture
def sample_pdf_text_no_abx():
    return """
    РАЗДЕЛ 2. ДИАГНОСТИКА

    Диагноз ставится на основании клинической картины и лабораторных данных.

    РАЗДЕЛ 3. ЛЕЧЕНИЕ

    Симптоматическая терапия. Постельный режим. Обильное питье.
    """


@pytest.fixture
def sample_pdf_text_keyword_only():
    return """
    РАЗДЕЛ 1. ОБЩИЕ СВЕДЕНИЯ

    Антибиотики не показаны при вирусных инфекциях.
    Рекомендуется посев мазка из зева.
    """


@pytest.fixture
def sample_item(tmp_path):
    # classifier.classify_one() only checks Path(pdf_path).exists() — every
    # test using this fixture mocks classifier.detect_sections, so the file
    # is never opened or parsed. A tiny, deterministic, repository-free
    # placeholder is sufficient; must NOT point outside the test's own
    # tmp_path (see TEST_FIXTURE_EXTERNAL_PATH_RCA.md).
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 TEST_FIXTURE_ONLY\n")
    return {
        "Id": 2199,
        "Name": "Внебольничная пневмония",
        "Code": 123,
        "Version": 6,
        "CodeVersion": "123_6",
        "Mkbs": [{"MkbCode": "J18", "MkbName": "Пневмония"}],
        "PublishDateStr": "2023-03-15",
        "has_antibiotics": True,
        "abx_drugs_found": ["амоксициллин", "азитромицин", "цефтриаксон"],
        "abx_keywords_found": ["антибактериальная терапия"],
        "abx_score": 35,
        "pdf_path": str(pdf_path),
    }


@pytest.fixture
def sample_regimen():
    return {
        "diagnosis": "Внебольничная пневмония",
        "mkb": "J18",
        "regimen_type": "first_line",
        "antibiotic": "амоксициллин",
        "antibiotic_normalized": "amoxicillin",
        "atc_code": "J01CA04",
        "dose": "500-1000",
        "dose_confidence": 0.96,
        "unit": "мг",
        "unit_confidence": 0.98,
        "frequency": "3 раза в день",
        "frequency_confidence": 0.95,
        "route": "внутрь",
        "route_confidence": 0.97,
        "duration": "7-10 дней",
        "duration_confidence": 0.87,
        "age_group": "взрослые",
        "age_group_confidence": 0.94,
        "weight_based": "нет",
        "renal_adjustment": "СКФ < 30: 250-500 мг 2 раза в день",
        "renal_confidence": 0.82,
        "pregnancy": "безопасно",
        "pregnancy_confidence": 0.90,
        "guideline_name": "Внебольничная пневмония",
        "code_version": "123_6",
        "pdf_file": "Внебольничная пневмония.pdf",
        "page_number": "12",
        "section_name": "Антибактериальная терапия",
        "source_quote": "Амоксициллин 500-1000 мг 3 раза в день внутрь в течение 7-10 дней",
        "extraction_confidence": 0.95,
    }


@pytest.fixture
def mock_llm_extract_response():
    return {
        "choices": [
            {
                "message": {
                    "content": '[{"diagnosis":"Пневмония","mkb":"J18","regimen_type":"first_line","antibiotic":"амоксициллин","antibiotic_normalized":"amoxicillin","atc_code":"J01CA04","dose":"500-1000","dose_confidence":0.96,"unit":"мг","unit_confidence":0.98,"frequency":"3 раза в день","frequency_confidence":0.95,"route":"внутрь","route_confidence":0.97,"duration":"7-10 дней","duration_confidence":0.87,"age_group":"взрослые","age_group_confidence":0.94,"weight_based":"нет","renal_adjustment":null,"renal_confidence":0.0,"pregnancy":"безопасно","pregnancy_confidence":0.90,"guideline_name":"Внебольничная пневмония","code_version":"123_6","pdf_file":"test.pdf","page_number":"12","section_name":"Антибактериальная терапия","source_quote":"Амоксициллин 500-1000 мг 3 раза в день","extraction_confidence":0.95}]'
                }
            }
        ]
    }


@pytest.fixture
def mock_llm_validate_response():
    return {
        "choices": [
            {
                "message": {
                    "content": '{"results":[{"index":0,"valid":true,"confidence":0.92,"issues":[],"corrected":null}]}'
                }
            }
        ]
    }


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_metadata.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE clinrecs (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            code INTEGER,
            version INTEGER,
            code_version TEXT UNIQUE
        );
        INSERT INTO clinrecs VALUES (2199, 'Тест', 123, 6, '123_6');
    """)
    conn.commit()
    conn.close()
    yield db_path
    if db_path.exists():
        db_path.unlink()
