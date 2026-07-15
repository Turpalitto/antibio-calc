"""Canonical curated-knowledge query layer + review-required engine gate (INT-4).

``CuratedKnowledge`` loads the generated ``curated_knowledge.json`` (built by
``build_curated_knowledge``) and answers approval queries. It NEVER silently
falls back: an unapproved diagnosis or regimen yields an explicit
:class:`ReviewRequired`, not an unapproved recommendation.

``CuratedEngine`` is an additive, opt-in wrapper around the existing ``Engine``.
It does not modify the engine, routing, or safety stages. In curated mode a
recommendation is returned only if its diagnosis routing AND its regimens are
physician-approved; otherwise the accepted list is suppressed and an explicit
``REVIEW_REQUIRED`` note is attached — so the engine never returns an unapproved
recommendation.

Provenance (requirement 4) is preserved end-to-end: an ``ApprovedChain`` links
diagnosis review → guideline_id → approved regimen_ids, each regimen carrying
pdf/page/SHA provenance copied from the curated regimen view.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_KNOWLEDGE = "clinical_engine/resources/curated_knowledge.json"


@dataclass(frozen=True, slots=True)
class ReviewRequired:
    """Explicit 'not physician-approved' outcome. Never a recommendation."""
    code: str            # NO_APPROVED_DIAGNOSIS | NO_APPROVED_REGIMEN | KNOWLEDGE_UNAVAILABLE
    reason: str
    diagnosis: str | None = None
    icd10: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovedChain:
    """A fully physician-approved diagnosis→regimen chain with provenance."""
    diagnosis: str | None
    icd10: str | None
    guideline_ids: tuple[str, ...]
    regimen_provenance: tuple[dict[str, Any], ...]  # provenance-only rows


class CuratedKnowledge:
    """Read-only view over the unified curated_knowledge.json."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self._doc = doc
        self._dx = doc.get("approved_diagnoses", [])
        self._reg = {r["regimen_id"]: r for r in doc.get("approved_regimens", [])}
        self._links = {l["guideline_id"]: l for l in doc.get("links", [])}

    # -- loading ---------------------------------------------------
    @classmethod
    def load(cls, path: str | Path = _DEFAULT_KNOWLEDGE) -> "CuratedKnowledge | None":
        p = Path(path)
        if not p.is_file():
            return None
        return cls(json.loads(p.read_text(encoding="utf-8")))

    # -- queries (never silently fall back) ------------------------
    def approved_guideline_ids(self, diagnosis: str | None, icd10: str | None) -> list[str]:
        d = (diagnosis or "").strip().lower()
        gids = [row["guideline_id"] for row in self._dx
                if str(row["diagnosis"]).strip().lower() == d and d]
        return sorted(set(gids))

    def approved_regimens_for(self, guideline_id: str) -> list[dict[str, Any]]:
        link = self._links.get(guideline_id)
        if not link:
            return []
        return [self._reg[rid] for rid in link.get("regimen_ids", []) if rid in self._reg]

    def resolve(self, diagnosis: str | None, icd10: str | None) -> ApprovedChain | ReviewRequired:
        gids = self.approved_guideline_ids(diagnosis, icd10)
        if not gids:
            return ReviewRequired(
                code="NO_APPROVED_DIAGNOSIS",
                reason="diagnosis has no physician-approved routing in the curated layer",
                diagnosis=diagnosis, icd10=icd10,
            )
        prov: list[dict[str, Any]] = []
        for gid in gids:
            prov.extend(self.approved_regimens_for(gid))
        if not prov:
            return ReviewRequired(
                code="NO_APPROVED_REGIMEN",
                reason=f"approved diagnosis routes to guideline(s) {gids} but no regimen is approved",
                diagnosis=diagnosis, icd10=icd10,
            )
        return ApprovedChain(
            diagnosis=diagnosis, icd10=icd10,
            guideline_ids=tuple(gids),
            regimen_provenance=tuple(prov),
        )

    def approved_regimen_ids(self) -> set[str]:
        return set(self._reg)


class CuratedEngine:
    """Opt-in curated-mode wrapper around Engine. Engine itself is unchanged.

    In curated mode a recommendation is returned only when the diagnosis routing
    AND every accepted regimen are physician-approved; otherwise an explicit
    review-required RecommendationSet is returned (empty accepted + note).
    """

    def __init__(self, engine: Any, knowledge: CuratedKnowledge | None) -> None:
        self._engine = engine
        self._knowledge = knowledge

    def recommend(self, query: Any):
        base = self._engine.recommend(query)

        # No curated knowledge available at all -> never emit unapproved recs.
        if self._knowledge is None:
            return self._review_required(
                base, "KNOWLEDGE_UNAVAILABLE",
                "curated knowledge layer not generated; no approved recommendations available")

        chain = self._knowledge.resolve(query.diagnosis, query.icd10)
        if isinstance(chain, ReviewRequired):
            return self._review_required(base, chain.code, chain.reason)

        # Diagnosis + guideline approved. Keep only accepted regimens that are
        # themselves physician-approved; never silently include unapproved ones.
        approved_ids = self._knowledge.approved_regimen_ids()
        kept = tuple(r for r in base.accepted
                     if getattr(r.candidate, "regimen_id", None) in approved_ids)
        if not kept:
            return self._review_required(
                base, "NO_APPROVED_REGIMEN",
                "no accepted regimen is physician-approved for this diagnosis")
        return self._annotated(base, kept, chain)

    # -- helpers ---------------------------------------------------
    @staticmethod
    def _note(code: str, message: str):
        from clinical_engine.models import EngineNote, NoteSeverity
        return EngineNote(code=code, message=message, stage="CuratedEngine",
                          severity=NoteSeverity.WARN)

    def _review_required(self, base, code: str, reason: str):
        note = self._note("REVIEW_REQUIRED", f"{code}: {reason}")
        return dataclasses.replace(base, accepted=(), engine_notes=base.engine_notes + (note,))

    def _annotated(self, base, kept, chain: ApprovedChain):
        # Attach a note recording the approved provenance chain; keep only approved recs.
        n_filtered = len(base.accepted) - len(kept)
        msg = (f"curated: {len(kept)} physician-approved regimen(s) for guideline(s) "
               f"{list(chain.guideline_ids)}"
               + (f"; {n_filtered} unapproved recommendation(s) withheld" if n_filtered else ""))
        note = self._note("CURATED_APPROVED", msg)
        return dataclasses.replace(base, accepted=kept, engine_notes=base.engine_notes + (note,))
