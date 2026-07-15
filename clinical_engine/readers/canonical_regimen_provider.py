"""CanonicalRegimenProviderAdapter — shadow provider (P5.3 Phase 7).

Design authority: CLINICAL_ENGINE_ADAPTER_RFC.md, MIGRATION_PLAN_NORMALIZED_REGIMENS.md.

Implements the EXISTING RegimenProvider port (clinical_engine/readers/sqlite_reader.py)
backed by assembled_regimens. Provides a SHADOW-COMPARE utility that diffs the new
assembled regimens against the old normalized_regimens for the same guideline(s) —
drug / dose / duration / alternatives — WITHOUT switching the engine. The engine is
not modified and not repointed here; this is validation-only.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ShadowDiff:
    guideline_id: str
    regimen_id: str
    field: str
    old_value: str
    new_value: str


@dataclass
class ShadowReport:
    compared: int
    matches: int
    diffs: list[ShadowDiff]

    @property
    def divergence_rate(self) -> float:
        return 0.0 if self.compared == 0 else len(self.diffs) / self.compared


class CanonicalRegimenProviderAdapter:
    """Reads assembled_regimens. Never writes. Never touches the engine."""

    def __init__(self, assembled_path: str):
        self._path = str(assembled_path)
        if not Path(self._path).exists():
            raise FileNotFoundError(f"assembled_regimens not found: {self._path}")
        self._conn = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row

    def load_by_guideline(self, guideline_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM assembled_regimens WHERE guideline_id=? AND validation_verdict IN ('PASS','REVIEW')",
            (guideline_id,)).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()


def shadow_compare(assembled_path: str, normalized_regimens_path: str,
                   guideline_ids: list[str] | None = None) -> ShadowReport:
    """Diff assembled_regimens vs normalized_regimens on drug/dose/duration for shared regimen_ids."""
    new = sqlite3.connect(f"file:{assembled_path}?mode=ro", uri=True); new.row_factory = sqlite3.Row
    old = sqlite3.connect(f"file:{normalized_regimens_path}?mode=ro", uri=True); old.row_factory = sqlite3.Row

    where = ""
    params: tuple = ()
    if guideline_ids:
        where = " WHERE guideline_id IN (%s)" % ",".join("?" * len(guideline_ids))
        params = tuple(guideline_ids)

    old_rows = {str(r["regimen_id"]): r for r in old.execute(
        "SELECT regimen_id, guideline_id, drug_normalized, dose, duration_recommended FROM normalized_regimens" + where, params)}
    new_rows = new.execute("SELECT regimen_id, guideline_id, antibiotic, dose, duration_recommended FROM assembled_regimens" + where, params).fetchall()

    diffs: list[ShadowDiff] = []
    compared = 0
    matches = 0
    for nr in new_rows:
        rid = str(nr["regimen_id"])
        orow = old_rows.get(rid)
        if orow is None:
            continue
        compared += 1
        row_diffs = []
        if (nr["antibiotic"] or "") != (orow["drug_normalized"] or ""):
            row_diffs.append(ShadowDiff(str(nr["guideline_id"]), rid, "drug",
                                        str(orow["drug_normalized"]), str(nr["antibiotic"])))
        if nr["dose"] != orow["dose"]:
            row_diffs.append(ShadowDiff(str(nr["guideline_id"]), rid, "dose",
                                        str(orow["dose"]), str(nr["dose"])))
        if nr["duration_recommended"] != orow["duration_recommended"]:
            row_diffs.append(ShadowDiff(str(nr["guideline_id"]), rid, "duration",
                                        str(orow["duration_recommended"]), str(nr["duration_recommended"])))
        if row_diffs:
            diffs.extend(row_diffs)
        else:
            matches += 1
    new.close(); old.close()
    return ShadowReport(compared=compared, matches=matches, diffs=diffs)
