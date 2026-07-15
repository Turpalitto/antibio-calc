"""DrugReferenceReader — db/index.json drugs_reference -> DrugInfo.

Source: docs/superpowers/specs/clinical-decision-engine-v1.md §3.5, §4.2.

Loads all DrugInfo once at init, caches in memory (§4.2 "Loads all DrugInfo
once at init, caches in memory (frozen dict)"). Single source of truth for
drug safety metadata — this reader creates no duplicate reference file.

Degraded-mode note (see DECISIONS.md 2026-07-10): most of drugs_reference's
renal_adjustment / interactions / contraindications fields are free text,
not structured data. This reader passes that text through unchanged on
DrugInfo — it does NOT parse it. The one exception is pregnancy_category,
whose enum type is fixed by the DrugInfo dataclass; it gets a narrow,
auditable keyword classification done once here at load time (preparation
time, not per-query runtime — same pattern the spec sanctions for
InteractionSeverity keywords in §6.4). contraindications and
pediatric_dosing are not present anywhere in db/index.json today, so they
are always None — degraded WARNING mode is expected downstream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from clinical_engine.models import (
    DilutionRoute,
    DrugForm,
    DrugInfo,
    EngineError,
    EngineErrorCode,
    PediatricDosing,
    PregnancyCategory,
)

# Known DilutionRoute fields — extra keys present in real data (e.g.
# "child_solvent_warning", "concentration_max_mg_ml") are not modeled in v1
# and are dropped (administration-guidance detail, not a safety input).
_DILUTION_FIELDS = {
    "solvent_options",
    "concentration_standard_mg_ml",
    "administration_time_min",
    "infusion_time_min",
    "contraindications",
    "cautions",
    "steps",
}


def _classify_pregnancy(raw_text: str | None) -> PregnancyCategory:
    """Narrow keyword classification — see DECISIONS.md 2026-07-10."""
    if not raw_text:
        return PregnancyCategory.UNKNOWN
    text = raw_text.strip()
    lowered = text.lower()
    if "триместр" in lowered:
        # Trimester-conditional (either direction) — Patient has no trimester
        # field, so neither PROHIBITED nor ALLOWED can be asserted safely.
        return PregnancyCategory.CAUTION
    if lowered.startswith("противопоказан"):
        return PregnancyCategory.PROHIBITED
    if lowered.startswith("разреш"):
        return PregnancyCategory.ALLOWED
    if lowered.startswith("с осторожностью"):
        return PregnancyCategory.CAUTION
    return PregnancyCategory.UNKNOWN


def _build_forms(raw_forms: Any) -> tuple[DrugForm, ...]:
    if not isinstance(raw_forms, list):
        return ()
    forms = []
    for f in raw_forms:
        if not isinstance(f, dict):
            continue
        forms.append(
            DrugForm(
                form_type=str(f.get("form_type") or ""),
                concentration=str(f.get("concentration") or ""),
                concentration_mg_per_ml=f.get("concentration_mg_per_ml"),
                notes=f.get("notes"),
            )
        )
    return tuple(forms)


def _build_dilution(raw_dilution: Any) -> dict[str, DilutionRoute]:
    if not isinstance(raw_dilution, dict):
        return {}
    result: dict[str, DilutionRoute] = {}
    for route_name, route_data in raw_dilution.items():
        if not isinstance(route_data, dict):
            continue
        kwargs = {k: v for k, v in route_data.items() if k in _DILUTION_FIELDS}
        solvent_options = kwargs.pop("solvent_options", ())
        steps = kwargs.pop("steps", ())
        result[route_name] = DilutionRoute(
            solvent_options=tuple(solvent_options) if solvent_options else (),
            steps=tuple(steps) if steps else (),
            **kwargs,
        )
    return result


def _build_pediatric_dosing(entry: dict[str, Any]) -> PediatricDosing | None:
    # No drug in db/index.json carries a "pediatric_dosing" key today
    # (known gap, see DECISIONS.md 2026-07-10). Kept as its own function so
    # wiring a future structured field requires touching only this spot.
    raw = entry.get("pediatric_dosing")
    if not isinstance(raw, dict):
        return None
    return PediatricDosing(
        mg_per_kg_day=raw.get("mg_per_kg_day"),
        max_daily_mg=raw.get("max_daily_mg"),
        weight_min_kg=raw.get("weight_min_kg"),
        weight_max_kg=raw.get("weight_max_kg"),
        age_min=raw.get("age_min"),
        age_max=raw.get("age_max"),
        freq_per_day=raw.get("freq_per_day"),
    )


class DrugReferenceReader:
    """Read-only access to drugs_reference. Never writes."""

    def __init__(self, drug_reference_path: str | Path) -> None:
        path = Path(drug_reference_path)
        if not path.exists():
            raise EngineError(
                EngineErrorCode.DRUG_REFERENCE_NOT_FOUND,
                f"drugs_reference not found: {path}",
                stage="HardSafetyFilter",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise EngineError(
                EngineErrorCode.RESOURCE_PARSE_ERROR, str(exc), stage="HardSafetyFilter"
            ) from exc

        drugs_reference = data.get("drugs_reference", {})
        self._by_ref: dict[str, DrugInfo] = {}
        self._synonym_to_ref: dict[str, str] = {}

        for key, entry in drugs_reference.items():
            if key.startswith("_") or not isinstance(entry, dict):
                continue  # e.g. "_note" metadata key, not a drug
            info = DrugInfo(
                drug_ref=key,
                inn=str(entry.get("inn") or ""),
                drug_class=str(entry.get("class") or ""),
                renal_adjustment=entry.get("renal_adjustment"),
                hepatic_adjustment=entry.get("hepatic_adjustment"),
                pregnancy_category=_classify_pregnancy(entry.get("pregnancy_category")),
                age_restriction_min=entry.get("age_restriction_min"),
                age_restriction_max=entry.get("age_restriction_max"),
                contraindications=entry.get("contraindications"),
                interactions=entry.get("interactions"),
                monitoring=entry.get("monitoring"),
                forms=_build_forms(entry.get("forms")),
                dilution=_build_dilution(entry.get("dilution")),
                pediatric_dosing=_build_pediatric_dosing(entry),
            )
            self._by_ref[key] = info
            self._synonym_to_ref[key.lower()] = key
            if info.inn:
                self._synonym_to_ref[info.inn.lower()] = key

    def get_drug_info(self, drug_ref: str) -> DrugInfo | None:
        return self._by_ref.get(drug_ref)

    def resolve_drug_ref(self, drug_normalized: str) -> str | None:
        return self._synonym_to_ref.get((drug_normalized or "").strip().lower())

    def get_interactions(self, drug_ref: str) -> str | None:
        info = self.get_drug_info(drug_ref)
        return info.interactions if info else None

    def get_pregnancy_category(self, drug_ref: str) -> PregnancyCategory | None:
        info = self.get_drug_info(drug_ref)
        return info.pregnancy_category if info else None

    def get_renal_adjustment(self, drug_ref: str) -> str | None:
        info = self.get_drug_info(drug_ref)
        return info.renal_adjustment if info else None


# P0-2: DrugSafetyProvider Protocol (public contract)
class DrugSafetyProvider(Protocol):
    def get_drug_info(self, drug_ref: str) -> DrugInfo | None: ...
    def resolve_drug_ref(self, drug_normalized: str) -> str | None: ...
    def get_interactions(self, drug_ref: str) -> str | None: ...
    def get_pregnancy_category(self, drug_ref: str) -> PregnancyCategory | None: ...
    def get_renal_adjustment(self, drug_ref: str) -> str | None: ...


# P0-2: Thin adapter. Wraps existing DrugReferenceReader. 100% identical delegation.
class DrugSafetyProviderAdapter(DrugSafetyProvider):
    """Adapter: existing reader behind DrugSafetyProvider port."""

    def __init__(self, reader: "DrugReferenceReader") -> None:
        self._reader = reader

    def get_drug_info(self, drug_ref: str) -> DrugInfo | None:
        return self._reader.get_drug_info(drug_ref)

    def resolve_drug_ref(self, drug_normalized: str) -> str | None:
        return self._reader.resolve_drug_ref(drug_normalized)

    def get_interactions(self, drug_ref: str) -> str | None:
        return self._reader.get_interactions(drug_ref)

    def get_pregnancy_category(self, drug_ref: str) -> PregnancyCategory | None:
        return self._reader.get_pregnancy_category(drug_ref)

    def get_renal_adjustment(self, drug_ref: str) -> str | None:
        return self._reader.get_renal_adjustment(drug_ref)
