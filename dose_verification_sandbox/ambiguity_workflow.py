"""Phase 11 — Ambiguity resolution workflow (RC-030).

Lets the owner perform a *source-fidelity* classification of an AMBIGUOUS or
UNPARSED DoseSemantics entry — e.g. "having read the PDF page myself, the
source text confirms per-day dosing" — without inventing a medical
interpretation. No resolution here can produce clinical approval; that
remains a separate, unimplemented gate (0 approved objects, by design).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from .semantics_models import AmbiguityResolution, RESOLUTION_TYPES

RESOLUTIONS_PATH = Path(__file__).parent / "data" / "ambiguity_resolutions.json"


def new_resolution_id() -> str:
    return f"ares_{uuid.uuid4().hex[:16]}"


def _load(path: Path = RESOLUTIONS_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save(items: list[dict], path: Path = RESOLUTIONS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def record_resolution(resolution: AmbiguityResolution, path: Path = RESOLUTIONS_PATH) -> AmbiguityResolution:
    items = _load(path)
    items.append(resolution.to_dict())
    _save(items, path)
    return resolution


def list_resolutions(path: Path = RESOLUTIONS_PATH, regimen_id: Optional[str] = None) -> list[dict]:
    items = _load(path)
    if regimen_id is not None:
        items = [i for i in items if i.get("regimen_id") == regimen_id]
    return items
