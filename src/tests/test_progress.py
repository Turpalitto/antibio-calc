from pathlib import Path
from unittest.mock import patch

import pytest

from progress import (
    load_progress,
    save_progress,
    needs_reprocessing,
    mark_extraction_done,
    mark_validation_done,
    get_pending_items,
)


def test_load_progress_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("progress.EXTRACTION_PROGRESS_JSON", tmp_path / "progress.json")
    data = load_progress()
    assert "items" in data
    assert data["items"] == {}


def test_save_and_load_progress(tmp_path, monkeypatch):
    monkeypatch.setattr("progress.EXTRACTION_PROGRESS_JSON", tmp_path / "progress.json")
    data = {"pipeline_version": "1.0", "items": {"2199": {"extraction_done": True}}}
    save_progress(data)
    loaded = load_progress()
    assert loaded["pipeline_version"] == "1.0"
    assert loaded["items"]["2199"]["extraction_done"] is True


def test_needs_reprocessing_new(tmp_path, monkeypatch):
    monkeypatch.setattr("progress.EXTRACTION_PROGRESS_JSON", tmp_path / "progress.json")
    assert needs_reprocessing(2199, "abc123") is True


def test_needs_reprocessing_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr("progress.EXTRACTION_PROGRESS_JSON", tmp_path / "progress.json")
    mark_extraction_done(2199, "abc123", 3)
    assert needs_reprocessing(2199, "abc123") is False


def test_needs_reprocessing_sha_changed(tmp_path, monkeypatch):
    monkeypatch.setattr("progress.EXTRACTION_PROGRESS_JSON", tmp_path / "progress.json")
    mark_extraction_done(2199, "abc123", 3)
    assert needs_reprocessing(2199, "newhash") is True


def test_mark_extraction_done(tmp_path, monkeypatch):
    monkeypatch.setattr("progress.EXTRACTION_PROGRESS_JSON", tmp_path / "progress.json")
    mark_extraction_done(2199, "abc123", 5)
    data = load_progress()
    assert data["items"]["2199"]["extraction_done"] is True
    assert data["items"]["2199"]["extraction_regimens_count"] == 5
    assert data["items"]["2199"]["pdf_sha256"] == "abc123"


def test_mark_validation_done(tmp_path, monkeypatch):
    monkeypatch.setattr("progress.EXTRACTION_PROGRESS_JSON", tmp_path / "progress.json")
    mark_validation_done(2199, 0.95)
    data = load_progress()
    assert data["items"]["2199"]["validation_done"] is True
    assert data["items"]["2199"]["validation_confidence"] == 0.95


def test_get_pending_items(tmp_path, monkeypatch):
    monkeypatch.setattr("progress.EXTRACTION_PROGRESS_JSON", tmp_path / "progress.json")
    mark_extraction_done(2199, "abc123", 3)
    items = [
        {"Id": 2199, "Name": "Done", "pdf_path": "/fake/path.pdf"},
        {"Id": 2200, "Name": "Pending", "pdf_path": "/fake/path2.pdf"},
    ]
    pending = get_pending_items(items)
    assert len(pending) == 1
    assert pending[0]["Id"] == 2200
