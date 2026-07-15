"""database.py — хранение метаданных (SQLite + JSON)."""

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import orjson

from config import ABX_JSON, DB_PATH, DOWNLOADS_ABX, DOWNLOADS_ALL, DOWNLOADS_OTHER
from downloader import sanitize_filename

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS clinrecs (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    code            INTEGER NOT NULL,
    version         INTEGER NOT NULL,
    code_version    TEXT    NOT NULL UNIQUE,
    mkb_codes       TEXT,
    mkb_names       TEXT,
    publish_date    TEXT,
    age_category    TEXT,
    developers      TEXT,
    status          TEXT,
    pdf_path        TEXT,
    pdf_sha256      TEXT,
    pdf_size        INTEGER,
    has_antibiotics INTEGER DEFAULT 0,
    abx_drugs       TEXT,
    abx_keywords    TEXT,
    abx_extra       TEXT,
    abx_score       INTEGER DEFAULT 0,
    category        TEXT DEFAULT 'unknown'
);

CREATE TABLE IF NOT EXISTS stats (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(DB_PATH))
    db.executescript(SCHEMA)
    return db


def _mkb_info(item: dict) -> tuple[str, str]:
    mkbs = item.get("Mkbs", []) or []
    codes = ", ".join(m.get("MkbCode", "") for m in mkbs if m.get("MkbCode"))
    names = ", ".join(m.get("MkbName", "") for m in mkbs if m.get("MkbName"))
    return codes, names


def _developers_str(item: dict) -> str:
    devs = item.get("Developers", []) or []
    return ", ".join(d.get("NkoName", "") for d in devs if d.get("NkoName"))


def _age_str(item: dict) -> str:
    ac = item.get("AgeCategoryStr", "")
    return ac if ac else str(item.get("AgeCategory", ""))


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def save_metadata(items: list[dict[str, Any]]) -> None:
    db = init_db()
    cur = db.cursor()

    for item in items:
        code_version = item.get("CodeVersion", "")
        mkb_codes, mkb_names = _mkb_info(item)

        pdf_path = item.get("pdf_path", "")
        pdf_sha256 = item.get("pdf_sha256", "")
        pdf_size = item.get("pdf_size") or 0

        # compute sha256 if missing but file exists
        if not pdf_sha256 and pdf_path:
            pdf_sha256 = sha256_file(Path(pdf_path))
            pdf_size = Path(pdf_path).stat().st_size if Path(pdf_path).exists() else 0

        has_abx = 1 if item.get("has_antibiotics") else 0
        abx_drugs = ", ".join(item.get("abx_drugs_found", []))
        abx_kw = ", ".join(item.get("abx_keywords_found", []))
        abx_ex = ", ".join(item.get("abx_extra_found", []))
        abx_score = item.get("abx_score", 0)
        category = item.get("category", "unknown")

        cur.execute(
            """INSERT OR REPLACE INTO clinrecs
            (id, name, code, version, code_version, mkb_codes, mkb_names,
             publish_date, age_category, developers, status,
             pdf_path, pdf_sha256, pdf_size,
             has_antibiotics, abx_drugs, abx_keywords, abx_extra, abx_score, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.get("Id"),
                item.get("Name") or "(unnamed)",
            item.get("Code") or 0,
            item.get("Version") or 0,
            code_version or f"unknown_{item.get('Id', 0)}",
                mkb_codes,
                mkb_names,
                item.get("PublishDateStr", ""),
                _age_str(item),
                _developers_str(item),
                "Действует" if item.get("Status") == 0 else "Не действует",
                pdf_path,
                pdf_sha256,
                pdf_size,
                has_abx,
                abx_drugs,
                abx_kw,
                abx_ex,
                abx_score,
                category,
            ),
        )

    db.commit()
    db.close()


def split_by_category(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Перемещает PDF: antibiotics → downloads_antibiotics, остальные → downloads_other."""
    import shutil

    DOWNLOADS_ABX.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_OTHER.mkdir(parents=True, exist_ok=True)

    for item in items:
        pdf_path_str = item.get("pdf_path", "")
        if not pdf_path_str:
            continue

        src = Path(pdf_path_str)
        if not src.exists():
            continue

        target_dir = DOWNLOADS_ABX if item.get("has_antibiotics") else DOWNLOADS_OTHER
        target_name = f"{sanitize_filename(item.get('Name', 'unnamed'))}.pdf"
        dst = target_dir / target_name

        if src != dst:
            shutil.copy2(src, dst)
            item["pdf_path"] = str(dst)
            item["category"] = "antibiotics" if item.get("has_antibiotics") else "other"

    return items


def save_antibiotic_json(items: list[dict[str, Any]]) -> None:
    abx_items = [it for it in items if it.get("has_antibiotics")]
    out: list[dict] = []
    for it in abx_items:
        out.append({
            "Name": it.get("Name"),
            "Code": it.get("Code"),
            "Version": it.get("Version"),
            "CodeVersion": it.get("CodeVersion"),
            "MKB": [{"code": m.get("MkbCode"), "name": m.get("MkbName")}
                     for m in (it.get("Mkbs") or [])],
            "PublishDate": it.get("PublishDateStr"),
            "AgeCategory": _age_str(it),
            "Developers": [d.get("NkoName") for d in (it.get("Developers") or [])],
            "pdf_path": it.get("pdf_path"),
            "pdf_sha256": it.get("pdf_sha256") or (
                sha256_file(Path(it["pdf_path"])) if it.get("pdf_path") else ""
            ),
            "abx_drugs_found": it.get("abx_drugs_found", []),
            "abx_keywords_found": it.get("abx_keywords_found", []),
            "abx_score": it.get("abx_score", 0),
        })

    ABX_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"  {ABX_JSON}: {len(out)} records")


REGIMENS_SCHEMA = """
CREATE TABLE IF NOT EXISTS antibiotic_regimens (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    clinrec_id              INTEGER,
    clinrec_name            TEXT,
    diagnosis               TEXT,
    mkb                     TEXT,
    regimen_type            TEXT,
    antibiotic              TEXT,
    antibiotic_normalized   TEXT,
    atc_code                TEXT,
    dose                    TEXT,
    dose_confidence         REAL,
    unit                    TEXT,
    unit_confidence         REAL,
    frequency               TEXT,
    frequency_confidence    REAL,
    route                   TEXT,
    route_confidence        REAL,
    duration                TEXT,
    duration_confidence     REAL,
    age_group               TEXT,
    age_group_confidence    REAL,
    weight_based            TEXT,
    renal_adjustment        TEXT,
    renal_confidence        REAL,
    pregnancy               TEXT,
    pregnancy_confidence    REAL,
    guideline_name          TEXT,
    code_version            TEXT,
    pdf_file                TEXT,
    pdf_sha256              TEXT,
    page_number             TEXT,
    section_name            TEXT,
    source_quote            TEXT,
    extraction_confidence   REAL,
    validation_confidence   REAL,
    validation_issues       TEXT,
    validated               INTEGER DEFAULT 0,
    publication_date        TEXT,
    extraction_version      TEXT,
    extraction_model        TEXT,
    validation_model        TEXT,
    extracted_at            TEXT,
    validated_at            TEXT,
    FOREIGN KEY (clinrec_id) REFERENCES clinrecs(id)
);

CREATE INDEX IF NOT EXISTS idx_regimens_diagnosis ON antibiotic_regimens(diagnosis);
CREATE INDEX IF NOT EXISTS idx_regimens_mkb ON antibiotic_regimens(mkb);
CREATE INDEX IF NOT EXISTS idx_regimens_antibiotic ON antibiotic_regimens(antibiotic);
CREATE INDEX IF NOT EXISTS idx_regimens_antibiotic_norm ON antibiotic_regimens(antibiotic_normalized);
CREATE INDEX IF NOT EXISTS idx_regimens_age ON antibiotic_regimens(age_group);
CREATE INDEX IF NOT EXISTS idx_regimens_code_version ON antibiotic_regimens(code_version);
CREATE INDEX IF NOT EXISTS idx_regimens_validated ON antibiotic_regimens(validated);
"""


def init_regimens_table(db: sqlite3.Connection) -> None:
    db.executescript(REGIMENS_SCHEMA)


def _sanitize(v: Any) -> Any:
    """Convert non-basic types to string for SQLite compatibility."""
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return json.dumps(v, ensure_ascii=False)


def save_regimens(db: sqlite3.Connection, regimens: list[dict]) -> None:
    init_regimens_table(db)
    # Clear before re-insert to avoid duplicates on re-run
    db.execute("DELETE FROM antibiotic_regimens")
    cur = db.cursor()
    for r in regimens:
        cur.execute(
            """INSERT INTO antibiotic_regimens (
                clinrec_id, clinrec_name, diagnosis, mkb, regimen_type,
                antibiotic, antibiotic_normalized, atc_code,
                dose, dose_confidence, unit, unit_confidence,
                frequency, frequency_confidence, route, route_confidence,
                duration, duration_confidence, age_group, age_group_confidence,
                weight_based, renal_adjustment, renal_confidence,
                pregnancy, pregnancy_confidence,
                guideline_name, code_version, pdf_file, pdf_sha256,
                page_number, section_name, source_quote,
                extraction_confidence, validation_confidence, validation_issues,
                validated, publication_date, extraction_version,
                extraction_model, validation_model, extracted_at, validated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _sanitize(r.get("clinrec_id")), _sanitize(r.get("clinrec_name")), _sanitize(r.get("diagnosis")), _sanitize(r.get("mkb")), _sanitize(r.get("regimen_type")),
                _sanitize(r.get("antibiotic")), _sanitize(r.get("antibiotic_normalized")), _sanitize(r.get("atc_code")),
                _sanitize(r.get("dose")), _sanitize(r.get("dose_confidence")), _sanitize(r.get("unit")), _sanitize(r.get("unit_confidence")),
                _sanitize(r.get("frequency")), _sanitize(r.get("frequency_confidence")), _sanitize(r.get("route")), _sanitize(r.get("route_confidence")),
                _sanitize(r.get("duration")), _sanitize(r.get("duration_confidence")), _sanitize(r.get("age_group")), _sanitize(r.get("age_group_confidence")),
                _sanitize(r.get("weight_based")), _sanitize(r.get("renal_adjustment")), _sanitize(r.get("renal_confidence")),
                _sanitize(r.get("pregnancy")), _sanitize(r.get("pregnancy_confidence")),
                _sanitize(r.get("guideline_name")), _sanitize(r.get("code_version")), _sanitize(r.get("pdf_file")), _sanitize(r.get("pdf_sha256")),
                _sanitize(r.get("page_number")), _sanitize(r.get("section_name")), _sanitize(r.get("source_quote")),
                _sanitize(r.get("extraction_confidence")), _sanitize(r.get("validation_confidence")),
                _sanitize(r.get("validation_issues")),
                _sanitize(r.get("validated", 0)), _sanitize(r.get("publication_date")), _sanitize(r.get("extraction_version")),
                _sanitize(r.get("extraction_model")), _sanitize(r.get("validation_model")),
                _sanitize(r.get("extracted_at")), _sanitize(r.get("validated_at")),
            ),
        )
    db.commit()


def load_validated_regimens(db: sqlite3.Connection) -> list[dict]:
    cur = db.execute("SELECT * FROM antibiotic_regimens WHERE validated = 1")
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def save_review_required(items: list[dict], path: Path = None) -> None:
    if path is None:
        from config import REVIEW_REQUIRED_JSON
        path = REVIEW_REQUIRED_JSON
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"  {path}: {len(items)} review items")
