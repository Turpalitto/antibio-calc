import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson

from config import EXTRACTION_MODEL, EXTRACTION_PROGRESS_JSON, EXTRACTION_VERSION, VALIDATION_MODEL

logger = logging.getLogger(__name__)

def _backup_path() -> Path:
    return EXTRACTION_PROGRESS_JSON.with_suffix(".progress.bak.json")


def _fsync_json(path: Path, data: dict) -> None:
    """Write JSON with fsync for crash safety."""
    blob = orjson.dumps(data, option=orjson.OPT_INDENT_2)
    path.write_bytes(blob)
    try:
        fd = os.open(str(path), os.O_RDONLY)
        os.fsync(fd)
        os.close(fd)
    except OSError:
        pass


def load_progress() -> dict:
    if not EXTRACTION_PROGRESS_JSON.exists():
        return {
            "pipeline_version": EXTRACTION_VERSION,
            "extraction_model": EXTRACTION_MODEL,
            "validation_model": VALIDATION_MODEL,
            "items": {},
        }
    try:
        raw = EXTRACTION_PROGRESS_JSON.read_bytes()
        return orjson.loads(raw)
    except (orjson.JSONDecodeError, IOError):
        # Try backup
        bk = _backup_path()
        if bk.exists():
            try:
                raw = bk.read_bytes()
                return orjson.loads(raw)
            except (orjson.JSONDecodeError, IOError):
                pass
        return {
            "pipeline_version": EXTRACTION_VERSION,
            "extraction_model": EXTRACTION_MODEL,
            "validation_model": VALIDATION_MODEL,
            "items": {},
        }


def save_progress(data: dict) -> None:
    _fsync_json(EXTRACTION_PROGRESS_JSON, data)


def needs_reprocessing(clinrec_id: int, pdf_sha256: str) -> bool:
    data = load_progress()
    key = str(clinrec_id)
    item = data["items"].get(key)
    if not item:
        return True
    if item.get("pdf_sha256") != pdf_sha256:
        return True
    if data.get("pipeline_version") != EXTRACTION_VERSION:
        return True
    if data.get("extraction_model") != EXTRACTION_MODEL:
        return True
    if data.get("validation_model") != VALIDATION_MODEL:
        return True
    return False


def mark_extraction_done(clinrec_id: int, sha256: str, count: int) -> None:
    data = load_progress()
    key = str(clinrec_id)
    if key not in data["items"]:
        data["items"][key] = {}
    data["items"][key].update({
        "pdf_sha256": sha256,
        "extraction_done": True,
        "extraction_at": datetime.now(timezone.utc).isoformat(),
        "extraction_regimens_count": count,
        "validation_done": False,
        "needs_reprocess": False,
    })
    data["pipeline_version"] = EXTRACTION_VERSION
    data["extraction_model"] = EXTRACTION_MODEL
    data["validation_model"] = VALIDATION_MODEL
    save_progress(data)


def mark_validation_done(clinrec_id: int, confidence: float) -> None:
    data = load_progress()
    key = str(clinrec_id)
    if key not in data["items"]:
        data["items"][key] = {}
    data["items"][key].update({
        "validation_done": True,
        "validation_at": datetime.now(timezone.utc).isoformat(),
        "validation_confidence": confidence,
    })
    save_progress(data)


def get_pending_items(items: list[dict]) -> list[dict]:
    data = load_progress()
    pending = []
    for item in items:
        clinrec_id = item.get("Id", 0)
        key = str(clinrec_id)
        entry = data["items"].get(key)
        if not entry or not entry.get("extraction_done"):
            pending.append(item)
    return pending
