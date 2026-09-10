"""Read-only access to the committed crosswalk artifact.

Fail-closed: a missing or malformed artifact raises rather than degrading to
"no links", because silently dropping provenance is exactly the failure class
this repository's invariants forbid (ARCHITECTURAL_INVARIANTS.md INV-01/INV-14).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Mapping

from .builder import (
    CrosswalkBuildError,
    DEFAULT_OUTPUT,
    icd_block,
    normalize_icd10_values,
    normalize_text,
)

__all__ = ["CalculatorCrosswalk", "CrosswalkBuildError"]


class CalculatorCrosswalk:
    """Immutable in-memory view of ``calculator_crosswalk.json``.

    All indices store integer positions into ``self._links`` so every lookup is
    O(1) per hit and every result preserves artifact order deterministically.
    """

    def __init__(self, artifact: Mapping[str, Any]) -> None:
        meta = artifact.get("meta")
        if not isinstance(meta, Mapping) or meta.get("artifact_type") != "CALCULATOR_GUIDELINE_CROSSWALK":
            raise CrosswalkBuildError("artifact_type must be CALCULATOR_GUIDELINE_CROSSWALK")
        links = artifact.get("links")
        if not isinstance(links, list):
            raise CrosswalkBuildError("crosswalk must contain links[]")
        unlinked = artifact.get("unlinked_guidelines")
        if unlinked is not None and not isinstance(unlinked, list):
            raise CrosswalkBuildError("unlinked_guidelines must be a list when present")
        self._meta: dict[str, Any] = dict(meta)
        self._links: tuple[dict[str, Any], ...] = tuple(dict(item) for item in links)
        self._unlinked_guidelines: tuple[dict[str, Any], ...] = tuple(
            dict(item) for item in (unlinked or ()) if isinstance(item, Mapping)
        )
        self._by_disease: dict[str, list[int]] = {}
        self._by_guideline: dict[str, list[int]] = {}
        self._by_title: dict[str, list[int]] = {}
        self._by_code: dict[str, list[int]] = {}
        self._by_block: dict[str, list[int]] = {}
        for position, link in enumerate(self._links):
            self._by_disease.setdefault(str(link.get("disease_id")), []).append(position)
            self._by_guideline.setdefault(str(link.get("guideline_id")), []).append(position)
            title_key = normalize_text(link.get("guideline_title"))
            if title_key:
                self._by_title.setdefault(title_key, []).append(position)
            for code in link.get("matched_icd10") or ():
                self._by_code.setdefault(str(code), []).append(position)
                block = icd_block(str(code))
                if block:
                    self._by_block.setdefault(block, []).append(position)

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str | Path = DEFAULT_OUTPUT) -> "CalculatorCrosswalk":
        p = Path(path)
        if not p.is_file():
            raise CrosswalkBuildError(
                f"crosswalk artifact not found: {p} — run "
                "`python -m clinical_engine.crosswalk.builder --write`"
            )
        try:
            artifact = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CrosswalkBuildError(f"crosswalk artifact is not readable JSON: {p}: {exc}") from exc
        if not isinstance(artifact, dict):
            raise CrosswalkBuildError(f"crosswalk artifact must be a JSON object: {p}")
        return cls(artifact)

    # ── metadata ────────────────────────────────────────────────────────────

    @property
    def meta(self) -> dict[str, Any]:
        return dict(self._meta)

    @property
    def purpose(self) -> str:
        return str(self._meta.get("purpose") or "")

    @property
    def warning(self) -> str:
        return str(self._meta.get("warning") or "")

    @property
    def coverage(self) -> dict[str, Any]:
        cov = self._meta.get("coverage")
        return dict(cov) if isinstance(cov, Mapping) else {}

    @property
    def links(self) -> tuple[dict[str, Any], ...]:
        return self._links

    @property
    def unlinked_guidelines(self) -> tuple[dict[str, Any], ...]:
        """Corpus guidelines no calculator disease reaches (mirror coverage)."""
        return self._unlinked_guidelines

    def __len__(self) -> int:
        return len(self._links)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._links)

    # ── lookups ─────────────────────────────────────────────────────────────

    def _select(self, positions: list[int]) -> list[dict[str, Any]]:
        return [dict(self._links[p]) for p in sorted(set(positions))]

    def for_disease(self, disease_id: str) -> list[dict[str, Any]]:
        return self._select(self._by_disease.get(str(disease_id), ()))

    def for_guideline(self, guideline_id: str) -> list[dict[str, Any]]:
        return self._select(self._by_guideline.get(str(guideline_id), ()))

    def for_icd10(self, code: str) -> list[dict[str, Any]]:
        """Links touching a code — exact code first, then its 3-char block."""
        positions: list[int] = []
        for normalized in normalize_icd10_values([code]):
            positions.extend(self._by_code.get(normalized, ()))
            block = icd_block(normalized)
            if block:
                positions.extend(self._by_block.get(block, ()))
        return self._select(positions)

    def for_title(self, title: str) -> list[dict[str, Any]]:
        return self._select(self._by_title.get(normalize_text(title), ()))

    def summary(self) -> dict[str, Any]:
        """Compact, physician-facing summary (no internal hashes)."""
        coverage = self.coverage
        return {
            "purpose": self.purpose,
            "warning": self.warning,
            "links": coverage.get("links", len(self._links)),
            "linked_diseases": coverage.get("linked_diseases"),
            "calculator_diseases": coverage.get("calculator_diseases"),
            "linked_guidelines": coverage.get("linked_guidelines"),
            "corpus_guidelines": coverage.get("corpus_guidelines"),
            "unlinked_guidelines": coverage.get("unlinked_guidelines"),
            "unmatched_diseases": coverage.get("unmatched_diseases"),
            "links_by_method": coverage.get("links_by_method"),
        }
