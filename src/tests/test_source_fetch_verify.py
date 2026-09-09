import asyncio
import json
from pathlib import Path

import pytest

from src.pipeline.extraction.regimen_candidates import GuidelineCandidateSpec, load_candidate_spec
from src.pipeline.extraction.source_fetch_verify import (
    dest_magic_is_pdf,
    fetch_and_verify_spec,
    verify_local_pdf,
)


PDF_BYTES = b"%PDF-1.7\n% fake official pdf\n"
OTHER_BYTES = b"<p>iisnode encountered an error when processing the request.</p>"

SPEC = {
    "guideline_id": "314_3",
    "guideline_title": "Отит средний острый",
    "approval_year": 2024,
    "source_url": "https://cr.minzdrav.gov.ru/view-cr/314_3",
    "diagnosis": "Острый средний отит",
    "icd10": ["H65.0", "H65.1", "H66.0"],
    "table_pages": [21, 22, 23],
    "duration": "7-10 days",
    "duration_page": 25,
    "duration_wording": "7-10 дней",
    "row_groups": [],
}


def _write_spec(dirpath: Path, *, expected_pdf_sha256: str = "") -> Path:
    payload = dict(SPEC)
    payload["expected_pdf_sha256"] = expected_pdf_sha256
    spec_path = dirpath / "314_3.json"
    spec_path.write_text(json.dumps(payload), encoding="utf-8")
    return spec_path


def _expected_sha(data: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(data).hexdigest()


@pytest.fixture
def spec_path(tmp_path: Path) -> Path:
    return _write_spec(tmp_path)


def test_fetch_verify_bridge_accepts_expected_pdf(tmp_path: Path):
    spec = load_candidate_spec(_write_spec(tmp_path, expected_pdf_sha256=_expected_sha(PDF_BYTES)))
    captured: list[tuple[str, Path]] = []

    async def downloader(code_version: str, dest_path: Path) -> tuple[bool, str, str]:
        captured.append((code_version, dest_path))
        dest_path.write_bytes(PDF_BYTES)
        return True, _expected_sha(PDF_BYTES)[len("sha256:"):], ""

    report = asyncio.run(fetch_and_verify_spec(
        spec,
        outdir=tmp_path / "out",
        downloader=downloader,
        captured_at="2026-09-02T00:00:00Z",
    ))
    assert report["guideline_id"] == "314_3"
    assert report["pdf_ok"] is True
    assert report["sha256_match"] is True
    assert report["verified"] is True
    assert captured == [("314_3", tmp_path / "out" / "CR_314_3.pdf")]


def test_fetch_verify_rejects_sha256_mismatch(tmp_path: Path):
    spec = load_candidate_spec(_write_spec(tmp_path, expected_pdf_sha256=_expected_sha(b"other")))

    async def downloader(code_version, dest_path):
        dest_path.write_bytes(PDF_BYTES)
        return True, _expected_sha(PDF_BYTES)[len("sha256:"):], ""

    report = asyncio.run(fetch_and_verify_spec(spec, outdir=tmp_path, downloader=downloader))
    assert report["pdf_ok"] is True
    assert report["sha256_match"] is False
    assert report["verified"] is False


def test_fetch_verify_reports_download_failure(tmp_path: Path):
    spec = load_candidate_spec(_write_spec(tmp_path, expected_pdf_sha256=_expected_sha(PDF_BYTES)))

    async def downloader(code_version, dest_path):
        return False, "60a1...", "Not a PDF: <p>iisnode error</p>"

    report = asyncio.run(fetch_and_verify_spec(spec, outdir=tmp_path, downloader=downloader))
    assert report["pdf_ok"] is False
    assert report["verified"] is False
    assert "iisnode" in report["error"]


@pytest.mark.parametrize("data,expected", [
    (b"%PDF-1.7", True),
    (b"<p>iisnode", False),
    (b"", False),
])
def test_dest_magic_is_pdf(tmp_path: Path, data: bytes, expected: bool):
    path = tmp_path / "f.bin"
    path.write_bytes(data)
    assert dest_magic_is_pdf(path) is expected


def test_verify_local_pdf_offline_mode(tmp_path: Path):
    pdf = tmp_path / "CR_314_3.pdf"
    pdf.write_bytes(PDF_BYTES)
    spec = load_candidate_spec(_write_spec(tmp_path, expected_pdf_sha256=_expected_sha(PDF_BYTES)))
    report = verify_local_pdf(spec, pdf_path=pdf)
    assert report["sha256_match"] is True
    assert report["pdf_magic"] is True
    assert report["verified"] is True


def test_verify_local_pdf_rejects_non_pdf(tmp_path: Path):
    pdf = tmp_path / "CR_314_3.pdf"
    pdf.write_bytes(OTHER_BYTES)
    spec = load_candidate_spec(_write_spec(tmp_path, expected_pdf_sha256=_expected_sha(OTHER_BYTES)))
    report = verify_local_pdf(spec, pdf_path=pdf)
    assert report["sha256_match"] is True
    assert report["pdf_magic"] is False
    assert report["verified"] is False
