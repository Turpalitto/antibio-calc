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
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from clinical_engine.models import DiagnosisEntry, EngineError, EngineErrorCode


class DiagnosisProvider(Protocol):
    def lookup(self, diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]: ...


@dataclass(frozen=True, slots=True)
class DiagnosisLookup:
    """Full result of a routing lookup, with provenance per signal (M-1).

    ``entries`` is the routing decision; ``by_diagnosis`` / ``by_icd10`` are the
    two independent signals so a stage can explain WHY a guideline was selected
    (Clinical Traceability Rule) instead of presenting a merged list whose
    provenance is unrecoverable.
    """

    entries: tuple[DiagnosisEntry, ...]
    by_diagnosis: tuple[DiagnosisEntry, ...]
    by_icd10: tuple[DiagnosisEntry, ...]
    # The two signals resolved to disjoint guideline sets: the query is
    # self-contradictory (e.g. name says community-acquired pneumonia, ICD says
    # something else). entries is empty and the caller must say so loudly.
    conflict: bool
    # More than one guideline produced the routing.
    mixed_provenance: bool

    @property
    def guideline_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(e.guideline_id for e in self.entries))


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

    def lookup_ex(self, diagnosis: str | None, icd10: str | None) -> DiagnosisLookup:
        """Match by exact diagnosis name (case-insensitive) and/or ICD-10 code.

        M-1: the two signals are no longer OR-ed into one anonymous list. When
        both are supplied they must AGREE — the routing is the intersection of
        the guideline sets each signal resolves to. A union silently merged
        unrelated guidelines into a single accepted list (a CAP query carrying
        ICD-10 J18.9 also picked up hospital-acquired pneumonia, because
        ``_normalize_icd`` reduces J18.9 to J18), and the result carried no
        record of which guideline each recommendation came from.

        Disjoint sets are a contradiction, not a merge: entries is empty and
        ``conflict`` is set, so the caller reports it instead of guessing which
        signal to believe. A signal that matches nothing does not conflict — it
        simply contributes nothing (that is how an ICD-typo degrades today).

        Not found on either -> empty list (Clinical no-data, not EngineError;
        DiagnosisMatch stage turns this into an engine_note, per §8.4).
        """
        by_name: list[DiagnosisEntry] = []
        by_icd: list[DiagnosisEntry] = []
        seen_name: set[str] = set()
        seen_icd: set[str] = set()

        if diagnosis is not None and diagnosis.strip():
            for entry in self._by_name.get(diagnosis.strip().lower(), ()):
                if entry.guideline_id not in seen_name:
                    by_name.append(entry)
                    seen_name.add(entry.guideline_id)

        if icd10 is not None and icd10.strip():
            # A stored base code ("J18") matches a more specific query
            # ("J18.9"): recall without the reverse direction, which would let a
            # bare "J18" claim every sub-code.
            for code in (icd10.strip().upper(), *_icd_base_codes(icd10)):
                for entry in self._by_icd10.get(code, ()):
                    if entry.guideline_id not in seen_icd:
                        by_icd.append(entry)
                        seen_icd.add(entry.guideline_id)

        if by_name and by_icd:
            agreed = [e for e in by_name if e.guideline_id in seen_icd]
            conflict = not agreed
            selected = agreed
        else:
            conflict = False
            selected = by_name or by_icd

        return DiagnosisLookup(
            entries=tuple(selected),
            by_diagnosis=tuple(by_name),
            by_icd10=tuple(by_icd),
            conflict=conflict,
            mixed_provenance=len({e.guideline_id for e in selected}) > 1,
        )

    def lookup(self, diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]:
        return list(self.lookup_ex(diagnosis, icd10).entries)


def _icd_base_codes(icd10: str | None) -> tuple[str, ...]:
    """Base code of a specific ICD-10 query ("J18.9" -> "J18")."""
    if not icd10:
        return ()
    code = icd10.strip().upper()
    if "." not in code:
        return ()
    return (code.split(".", 1)[0],)


# P0-2: Explicit thin adapter for completeness (JsonDiagnosisProvider already satisfies Protocol directly).
class DiagnosisProviderAdapter(DiagnosisProvider):
    """Adapter: wraps JsonDiagnosisProvider (or any impl). 100% delegation."""

    def __init__(self, reader: "JsonDiagnosisProvider") -> None:
        self._reader = reader

    def lookup(self, diagnosis: str | None, icd10: str | None) -> list[DiagnosisEntry]:
        return self._reader.lookup(diagnosis, icd10)

    def lookup_ex(self, diagnosis: str | None, icd10: str | None) -> DiagnosisLookup:
        return self._reader.lookup_ex(diagnosis, icd10)
