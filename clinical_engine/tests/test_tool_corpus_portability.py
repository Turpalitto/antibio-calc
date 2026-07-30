import json
from pathlib import Path

import build_p44_kb
import production_reprocessor
import reprocess_p45_layout


def _corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "external-corpus"
    active = corpus / "downloads_active"
    active.mkdir(parents=True)
    (active / "example.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 2048)
    (corpus / "knowledge_base.json").write_text(
        json.dumps(
            [
                {
                    "pdf_file": "example.pdf",
                    "clinrec_id": "test-guideline",
                }
            ]
        ),
        encoding="utf-8",
    )
    return corpus


def test_p44_build_helpers_accept_external_corpus_root(tmp_path):
    corpus = _corpus(tmp_path)

    assert build_p44_kb.load_contributing_pdfs(corpus_dir=corpus) == [
        corpus / "downloads_active" / "example.pdf"
    ]
    assert build_p44_kb.load_guideline_id_map(corpus_dir=corpus) == {
        "example.pdf": "test-guideline"
    }


def test_reprocessors_accept_external_corpus_root(tmp_path):
    corpus = _corpus(tmp_path)
    expected = [corpus / "downloads_active" / "example.pdf"]

    assert production_reprocessor.load_contributing_pdfs(corpus) == expected
    assert reprocess_p45_layout.load_contributing_pdfs(
        corpus_dir=corpus
    ) == expected


def test_executable_tools_do_not_embed_workstation_corpus_path():
    root = Path(__file__).resolve().parents[2]
    paths = [
        root / "build_review_workbench.py",
        root / "build_p44_kb.py",
        root / "production_reprocessor.py",
        root / "reprocess_p45_layout.py",
        root / "validate_full_corpus.py",
        root / "clinical_engine" / "tools" / "build_normalized_sqlite.py",
        root / "clinical_engine" / "tools" / "clinical_data_audit.py",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "C:\\clinrec_downloader" not in source
        assert "C:/clinrec_downloader" not in source
