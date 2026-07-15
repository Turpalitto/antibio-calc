"""DiagnosisProvider Protocol + JsonDiagnosisProvider.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §3.4, §4.2,
§11 ("DiagnosisProvider | Protocol | v1 | Diagnosis source (JSON -> SQLite
-> API), engine doesn't change").

Two accepted JSON shapes (backward compatible):
  1. A bare list of entry objects (test fixtures use this).
  2. An object ``{"meta": {...}, "entries": [ ...entry objects... ]}`` —
     used by the AUTO_GENERATED_DRAFT production index
     (clinical_engine/resources/diagnosis_index.json, built by
     tools/build_diagnosis_index_draft.py). The ``meta`` block carries
     status/guideline_set_version; the reader only consumes ``entries``.

Entry shape (one per diagnosis/guideline mapping):
    {
      "guideline_id": "...",
      "diagnosis_name": "...",
      "icd10_codes": ["J18", ...],
      "guideline_title": "...",
      "guideline_year": 2024,
      "guideline_revision_date": "2024-03-15",
      "source_url": "https://..."
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from clinical_engine.models import DiagnosisEntry, EngineError, EngineErrorCode


class DiagnosisProvider(Protocol):
    def lookup(self, diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]: ...


class JsonDiagnosisProvider:
    """v1 implementation — loads the whole index once, caches in memory."""

    def __init__(self, diagnosis_index_path: str | Path) -> None:
        path = Path(diagnosis_index_path)
        if not path.exists():
            raise EngineError(
                EngineErrorCode.DIAGNOSIS_INDEX_NOT_FOUND,
                f"diagnosis_index not found: {path}",
                stage="DiagnosisMatch",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise EngineError(
                EngineErrorCode.RESOURCE_PARSE_ERROR, str(exc), stage="DiagnosisMatch"
            ) from exc

        # Accept a bare list (fixtures) or {"meta": ..., "entries": [...]} (draft).
        if isinstance(data, dict) and "entries" in data:
            self.meta: dict = data.get("meta") or {}
            raw_entries = data["entries"]
        elif isinstance(data, list):
            self.meta = {}
            raw_entries = data
        else:
            raise EngineError(
                EngineErrorCode.RESOURCE_PARSE_ERROR,
                f"diagnosis_index must be a JSON array or an object with 'entries': {path}",
                stage="DiagnosisMatch",
            )
        if not isinstance(raw_entries, list):
            raise EngineError(
                EngineErrorCode.RESOURCE_PARSE_ERROR,
                f"diagnosis_index 'entries' must be a JSON array: {path}",
                stage="DiagnosisMatch",
            )

        self._entries: list[DiagnosisEntry] = [
            DiagnosisEntry(
                guideline_id=str(e["guideline_id"]),
                diagnosis_name=str(e.get("diagnosis_name") or ""),
                icd10_codes=tuple(e.get("icd10_codes") or ()),
                guideline_title=str(e.get("guideline_title") or ""),
                guideline_year=e.get("guideline_year"),
                guideline_revision_date=e.get("guideline_revision_date"),
                source_url=str(e.get("source_url") or ""),
            )
            for e in raw_entries
        ]
        self._by_name: dict[str, list[DiagnosisEntry]] = {}
        self._by_icd10: dict[str, list[DiagnosisEntry]] = {}
        for entry in self._entries:
            self._by_name.setdefault(entry.diagnosis_name.strip().lower(), []).append(entry)
            for code in entry.icd10_codes:
                self._by_icd10.setdefault(code.strip().upper(), []).append(entry)

    def lookup(self, diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]:
        """Match by exact diagnosis name (case-insensitive) or ICD-10 code.

        Not found on either -> empty list (Clinical no-data, not EngineError;
        DiagnosisMatch stage turns this into an engine_note, per §8.4).
        """
        matches: list[DiagnosisEntry] = []
        seen: set[str] = set()

        if diagnosis is not None:
            for entry in self._by_name.get(diagnosis.strip().lower(), ()):
                if entry.guideline_id not in seen:
                    matches.append(entry)
                    seen.add(entry.guideline_id)

        if icd10 is not None:
            for entry in self._by_icd10.get(icd10.strip().upper(), ()):
                if entry.guideline_id not in seen:
                    matches.append(entry)
                    seen.add(entry.guideline_id)

        return matches


# P0-2: Explicit thin adapter for completeness (JsonDiagnosisProvider already satisfies Protocol directly).
class DiagnosisProviderAdapter(DiagnosisProvider):
    """Adapter: wraps JsonDiagnosisProvider (or any impl). 100% delegation."""

    def __init__(self, reader: "JsonDiagnosisProvider") -> None:
        self._reader = reader

    def lookup(self, diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]:
        return self._reader.lookup(diagnosis, icd10)
