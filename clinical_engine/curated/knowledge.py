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

Approval identity: ``normalized_regimens`` declares
``PRIMARY KEY (guideline_id, regimen_id)`` — a regimen_id is NOT globally
unique. The gate is therefore keyed on the (guideline_id, regimen_id) pair, and
an approval only counts for the guideline the routing actually resolved to.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_KNOWLEDGE = "clinical_engine/resources/curated_knowledge.json"

# Key of an approved regimen: (guideline_id, regimen_id). See module docstring.
RegimenKey = tuple[str, str]


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

    def approved_keys(self) -> set[RegimenKey]:
        """(guideline_id, regimen_id) pairs this approval actually covers."""
        return {
            (str(row.get("guideline_id", "")), str(row["regimen_id"]))
            for row in self.regimen_provenance
            if row.get("regimen_id")
        }


class CuratedKnowledge:
    """Read-only view over the unified curated_knowledge.json."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self._doc = doc
        self._dx = doc.get("approved_diagnoses", [])
        # Keyed by (guideline_id, regimen_id): regimen_id alone is not unique
        # (NormalizerDB PRIMARY KEY is the pair), so a single-dict-by-id would
        # silently drop one of two same-id regimens from different guidelines.
        self._reg: dict[RegimenKey, dict[str, Any]] = {
            (str(r.get("guideline_id", "")), str(r["regimen_id"])): r
            for r in doc.get("approved_regimens", [])
        }
        self._links = {l["guideline_id"]: l for l in doc.get("links", [])}
        self._dx_by_icd: dict[str, list[str]] = {}
        for row in self._dx:
            for code in _row_icd_codes(row):
                self._dx_by_icd.setdefault(code, []).append(str(row.get("diagnosis") or ""))

    # -- loading ---------------------------------------------------
    @classmethod
    def load(cls, path: str | Path = _DEFAULT_KNOWLEDGE) -> "CuratedKnowledge | None":
        p = Path(path)
        if not p.is_file():
            return None
        return cls(json.loads(p.read_text(encoding="utf-8")))

    # -- queries (never silently fall back) ------------------------
    def approved_guideline_ids(self, diagnosis: str | None, icd10: str | None) -> list[str]:
        """Guidelines approved for a diagnosis name and/or an ICD-10 code.

        M-5: the icd10 argument used to be accepted and ignored, and the
        ``and d`` guard made an empty diagnosis return []. Since
        api/contract.py explicitly permits an ICD-only query, EVERY such
        request failed closed with NO_APPROVED_DIAGNOSIS. An approved row may
        now carry its ICD-10 codes (``icd10`` / ``icd10_codes``), and they are
        indexed and matched. The two signals must agree when both are given —
        same rule as the diagnosis index (M-1).
        """
        by_name: set[str] = set()
        d = (diagnosis or "").strip().lower()
        if d:
            by_name = {
                str(row["guideline_id"])
                for row in self._dx
                if str(row.get("diagnosis") or "").strip().lower() == d
            }

        by_icd: set[str] = set()
        i = (icd10 or "").strip().upper()
        if i:
            names = set(self._dx_by_icd.get(i, ()))
            base = i.split(".", 1)[0]
            if "." in i:
                names |= set(self._dx_by_icd.get(base, ()))
            for row in self._dx:
                if str(row.get("diagnosis") or "") in names:
                    by_icd.add(str(row["guideline_id"]))

        if by_name and by_icd:
            return sorted(by_name & by_icd)
        return sorted(by_name or by_icd)

    def approved_diagnoses_for_icd10(self, icd10: str | None) -> list[str]:
        """Approved diagnosis NAMES an ICD-10 code maps to (M-5 helper)."""
        if not (icd10 or "").strip():
            return []
        i = icd10.strip().upper()
        names = set(self._dx_by_icd.get(i, ()))
        if "." in i:
            names |= set(self._dx_by_icd.get(i.split(".", 1)[0], ()))
        return sorted(n for n in names if n)

    def approved_regimens_for(self, guideline_id: str) -> list[dict[str, Any]]:
        link = self._links.get(guideline_id)
        if not link:
            return []
        return [
            row
            for row in (
                self._reg.get((guideline_id, str(rid)))
                for rid in link.get("regimen_ids", [])
            )
            if row is not None
        ]

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

    def approved_regimen_keys(self) -> set[RegimenKey]:
        """Every approved (guideline_id, regimen_id) pair, globally."""
        return set(self._reg)


def _row_icd_codes(row: dict[str, Any]) -> tuple[str, ...]:
    """ICD-10 codes carried by an approved_diagnoses row, if any."""
    raw = row.get("icd10_codes")
    if raw is None:
        raw = row.get("icd10")
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    return tuple(str(c).strip().upper() for c in raw if str(c).strip())


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

        chain = self._resolve_chain(query, base)
        if isinstance(chain, ReviewRequired):
            return self._review_required(base, chain.code, chain.reason)

        # Diagnosis + guideline approved. A regimen is approved only under the
        # guideline the routing actually resolved to: regimen_id is unique only
        # within a guideline (NormalizerDB PK is the pair), so a global id set
        # let an UNAPPROVED "r1" of guideline B pass because "r1" was approved
        # for guideline A.
        approved = chain.approved_keys()
        kept, withheld = [], []
        for rec in base.accepted:
            candidate = getattr(rec, "candidate", None)
            key = (
                str(getattr(candidate, "guideline_id", "")),
                str(getattr(candidate, "regimen_id", "")),
            )
            if key in approved:
                kept.append(rec)
            else:
                withheld.append((rec, f"curated: {key[1]} is not approved under guideline {key[0]}"))
        if not kept:
            return self._review_required(
                base, "NO_APPROVED_REGIMEN",
                "no accepted regimen is physician-approved for this diagnosis")
        return self._annotated(base, kept, withheld, chain)

    # -- helpers ---------------------------------------------------
    def _resolve_chain(self, query: Any, base: Any) -> ApprovedChain | ReviewRequired:
        """Resolve the approval chain, including ICD-only queries (M-5)."""
        assert self._knowledge is not None
        chain = self._knowledge.resolve(getattr(query, "diagnosis", None),
                                       getattr(query, "icd10", None))
        if not isinstance(chain, ReviewRequired):
            return chain
        icd = getattr(query, "icd10", None)
        diagnosis = getattr(query, "diagnosis", None)
        if diagnosis or not icd:
            return chain
        # ICD-only request. curated_knowledge.json keys approvals by diagnosis
        # NAME, so the code is mapped to the names the routing index knows and
        # each is looked up separately. Still fail-closed if none is approved.
        names = self._knowledge.approved_diagnoses_for_icd10(icd)
        if not names:
            # Fall back to the engine's own index for the code->name mapping.
            names = list(self._engine.guideline_diagnosis_names(icd)) if hasattr(
                self._engine, "guideline_diagnosis_names"
            ) else []
        merged: list[ApprovedChain] = []
        for name in names:
            sub = self._knowledge.resolve(name, icd)
            if isinstance(sub, ApprovedChain):
                merged.append(sub)
        if not merged:
            return chain
        gids = tuple(dict.fromkeys(g for sub in merged for g in sub.guideline_ids))
        prov: dict[tuple[str, str], dict[str, Any]] = {}
        for sub in merged:
            for row in sub.regimen_provenance:
                prov[(str(row.get("guideline_id", "")), str(row["regimen_id"]))] = row
        return ApprovedChain(
            diagnosis=diagnosis, icd10=icd,
            guideline_ids=gids,
            regimen_provenance=tuple(prov.values()),
        )

    @staticmethod
    def _note(code: str, message: str):
        from clinical_engine.models import EngineNote, NoteSeverity
        return EngineNote(code=code, message=message, stage="CuratedEngine",
                          severity=NoteSeverity.WARN)

    def _review_required(self, base, code: str, reason: str):
        note = self._note("REVIEW_REQUIRED", f"{code}: {reason}")
        return dataclasses.replace(base, accepted=(), engine_notes=base.engine_notes + (note,))

    def _annotated(self, base, kept, withheld, chain: ApprovedChain):
        """Return a result set that describes EXACTLY what it returns (M-6).

        The old version replaced `accepted` only: `excluded`, `warnings`,
        `safety_flags`, `traces` and `rank` still described the PRE-FILTER set,
        so a consumer reading the flags saw warnings for recommendations that
        were no longer present and a rank sequence with holes. Now:
          - withheld recommendations move into `excluded` with a reason
            (nothing a physician saw disappear without explanation);
          - flags are narrowed to the drugs actually returned;
          - `rank` is renumbered 1..N over the returned set;
          - the note names both the kept and the withheld regimens.
        """
        from clinical_engine.models import SafetyLevel

        n_filtered = len(withheld)
        msg = (f"curated: {len(kept)} physician-approved regimen(s) for guideline(s) "
               f"{list(chain.guideline_ids)}"
               + (f"; {n_filtered} unapproved recommendation(s) withheld" if n_filtered else ""))
        note = self._note("CURATED_APPROVED", msg)

        kept_refs = {
            getattr(getattr(r, "candidate", None), "drug_ref", None) for r in kept
        }
        kept_refs.discard(None)

        def _flag_kept(flag) -> bool:
            return not flag.drug_ref or flag.drug_ref in kept_refs

        flags = tuple(f for f in base.safety_flags if _flag_kept(f))
        warnings = tuple(
            f for f in base.warnings
            if f.level is SafetyLevel.WARNING and _flag_kept(f)
        )
        renumbered = tuple(
            dataclasses.replace(r, rank=i) for i, r in enumerate(kept, start=1)
        )
        from clinical_engine.models import SafetySummary

        return dataclasses.replace(
            base,
            accepted=renumbered,
            excluded=tuple(base.excluded) + tuple(withheld),
            safety_flags=flags,
            warnings=warnings,
            engine_notes=base.engine_notes + (note,),
            safety_summary=SafetySummary.from_result(flags, renumbered),
        )
