"""SQLiteReader — normalized_regimens rows -> RecommendationCandidate.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §3.6, §4.2.

Wraps the FROZEN medical_normalizer.db.NormalizerDB — does not reopen
sqlite3 directly or duplicate its schema/SQL. One connection is opened at
init and reused (spec §9.2 "SQLite connection reuse").

``drug_ref`` and ``guideline_year`` on the returned candidates are always
None here: drug_ref resolution belongs to DrugReferenceReader (§3.5,
resolved later by stage code), and guideline_year comes from DiagnosisEntry
(diagnosis_index), not from SQLite (per RecommendationCandidate field
comment in §5.3). RegimenLoad (Milestone 3) fills both in via
dataclasses.replace() once DiagnosisMatch has run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from medical_normalizer.db import NormalizerDB, RegimenRecord

from clinical_engine.models import (
    EngineError,
    EngineErrorCode,
    RecommendationCandidate,
    ValidationPolicy,
)

# §3.6 ValidationPolicy -> which validation_verdict values are loaded
_VERDICTS_BY_POLICY: dict[ValidationPolicy, frozenset[str] | None] = {
    ValidationPolicy.STRICT: frozenset({"PASS"}),
    ValidationPolicy.ALLOW_REVIEW: frozenset({"PASS", "REVIEW"}),
    ValidationPolicy.DEBUG: None,  # None == no filter, all verdicts
    ValidationPolicy.AUDIT: None,
}


class SQLiteReader:
    """Read-only access to ``normalized_regimens``. Never writes."""

    def __init__(self, sqlite_path: str | Path) -> None:
        self._sqlite_path = str(sqlite_path)
        if not Path(self._sqlite_path).exists():
            raise EngineError(
                EngineErrorCode.SQLITE_NOT_FOUND,
                f"SQLite file not found: {self._sqlite_path}",
                stage="RegimenLoad",
            )
        try:
            self._db = NormalizerDB.connect(self._sqlite_path)
        except Exception as exc:  # pragma: no cover - defensive, sqlite3 rarely raises here
            raise EngineError(
                EngineErrorCode.SQLITE_CORRUPT, str(exc), stage="RegimenLoad"
            ) from exc
        if not self._db.table_exists():
            raise EngineError(
                EngineErrorCode.SQLITE_CORRUPT,
                f"normalized_regimens table missing in {self._sqlite_path}",
                stage="RegimenLoad",
            )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "SQLiteReader":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def load_regimens(
        self,
        guideline_ids: tuple[str, ...],
        policy: ValidationPolicy = ValidationPolicy.STRICT,
    ) -> list[RecommendationCandidate]:
        """Load candidates for the given guideline_ids, filtered by policy.

        AUDIT and DEBUG both load every verdict here — AUDIT's "no clinical
        filters" behavior (bypassing safety stages) is a RegimenLoad-and-later
        concern for the engine orchestrator, not this reader.
        """
        allowed_verdicts = _VERDICTS_BY_POLICY[policy]
        candidates: list[RecommendationCandidate] = []
        for guideline_id in guideline_ids:
            records = self._db.load_by_guideline(guideline_id)
            for record in records:
                if allowed_verdicts is not None and record.validation_verdict not in allowed_verdicts:
                    continue
                candidates.append(self._to_candidate(record))
        return candidates

    @staticmethod
    def _to_candidate(record: RegimenRecord) -> RecommendationCandidate:
        """Map a RegimenRecord (SQLite row) to a RecommendationCandidate.

        Validates/coerces types at read time — guards against corrupt rows
        (e.g. a NULL where the domain object expects a string).
        """
        raw = record.raw
        return RecommendationCandidate(
            regimen_id=record.regimen_id,
            guideline_id=record.guideline_id,
            drug_normalized=record.drug_normalized or "",
            drug_ref=None,  # resolved later via DrugReferenceReader.resolve_drug_ref()
            dose=record.dose,
            dose_unit=record.dose_unit or "",
            route=record.route or "unknown",
            frequency=record.frequency,
            duration_min=record.duration_min,
            duration_max=record.duration_max,
            duration_recommended=record.duration_recommended,
            therapy_line=record.therapy_line or "unknown",
            adult=bool(record.adult),
            child=bool(record.child),
            pregnancy=record.pregnancy,
            renal_adjustment=bool(record.renal_adjustment),
            atc_code=record.atc_code or "",
            confidence=float(record.overall_confidence),
            validation_verdict=record.validation_verdict or "REJECT",
            source_pdf=record.source_pdf or "",
            source_page=record.source_page or "",
            source_quote=str(raw.get("source_quote") or ""),
            source_section="",  # v1: SQLite lacks this column (see §5.3)
            diagnosis=record.diagnosis or "",
            mkb=record.mkb or "",
            guideline_year=None,  # filled from DiagnosisEntry by RegimenLoad stage
        )


# P0-2: RegimenProvider Protocol (public contract)
class RegimenProvider(Protocol):
    def load_regimens(
        self, guideline_ids: tuple[str, ...], policy: ValidationPolicy = ValidationPolicy.STRICT
    ) -> list[RecommendationCandidate]: ...


# P0-2: Thin adapter. Wraps existing SQLiteReader. 100% identical delegation. No new logic.
class RegimenProviderAdapter(RegimenProvider):
    """Adapter: existing reader behind RegimenProvider port."""

    def __init__(self, reader: "SQLiteReader") -> None:
        self._reader = reader

    def load_regimens(
        self, guideline_ids: tuple[str, ...], policy: ValidationPolicy = ValidationPolicy.STRICT
    ) -> list[RecommendationCandidate]:
        return self._reader.load_regimens(guideline_ids, policy)
