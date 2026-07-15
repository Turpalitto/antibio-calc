"""TerminologyProvider for P1.

Additive wrapper over current data + future ATC.

Protocol + basic impl using ClinicalConstants + medical_dictionary.

Clinical value: ATC standardization for allergy, diagnosis binding.
P1-B: diagnosis synonym + ICD normalization for routing accuracy + full traceability.

Supports Clinical Traceability Rule (point 4: record mapping source).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from clinical_engine.pipeline import ClinicalConstants


class TerminologyProvider(Protocol):
    def get_atc(self, drug_ref: str) -> str | None: ...
    def get_allergy_class(self, drug_ref: str) -> str | None: ...
    def resolve_diagnosis(self, diagnosis: str | None, icd10: str | None) -> list[str]: ...
    def normalize_diagnosis(self, diagnosis: str | None, icd10: str | None) -> "DiagnosisNormalization | None": ...


@dataclass
class TerminologyMapping:
    """For traceability: which source used."""
    source: str  # "drug_atc", "allergy_class_map", "synonym"
    key: str
    value: str | None


@dataclass(frozen=True, slots=True)
class DiagnosisNormalization:
    """P1-B: full traceable output for every diagnosis normalization decision.
    Used to improve lookup and explain to physician / audit.
    """
    original_diagnosis: str | None
    original_icd: str | None
    normalized_diagnosis: str | None
    normalized_icd: str | None
    synonym_used: str | None
    icd_mapping: str | None
    confidence: str  # "HIGH" | "MEDIUM" | "LOW"
    reason: str
    source: str


class BasicTerminologyProvider:
    """Current impl. Additive. Uses constants map.
    ATC from drug_atc when populated (currently empty).
    """

    def __init__(self, constants: ClinicalConstants) -> None:
        self._allergy_map: dict[str, str] = constants.allergy_class_map
        self._atc_map: dict[str, str] = {}
        # Load if possible (future data). load_drug_atc() is @lru_cache'd — copy
        # before mutating below, or every instance corrupts the shared cached dict.
        try:
            from medical_dictionary.loader import load_drug_atc  # type: ignore
            self._atc_map = dict(load_drug_atc())
        except Exception:
            self._atc_map = {}
        # P1 demo for clinical validation: sample atc to demonstrate hierarchy (J01C -> Пенициллины)
        self._atc_map.setdefault("unmapped_pen", "J01CA04")

        # P1-B: diagnosis synonyms (data-driven, additive). Direct load to avoid P0 mod to loader.
        self._diagnosis_synonyms: dict[str, str] = {}
        try:
            import json
            from pathlib import Path
            base = Path(__file__).resolve().parent.parent
            p = base / "medical_dictionary" / "diagnosis_synonyms.json"
            data = json.loads(p.read_text(encoding="utf-8"))
            self._diagnosis_synonyms = dict(data.get("entries", {}))
        except Exception:
            self._diagnosis_synonyms = {}

    def get_atc(self, drug_ref: str) -> str | None:
        if not drug_ref:
            return None
        return self._atc_map.get(drug_ref.lower())

    def get_allergy_class(self, drug_ref: str) -> str | None:
        if not drug_ref:
            return None
        if drug_ref in self._allergy_map:
            return self._allergy_map[drug_ref]
        atc = self.get_atc(drug_ref)
        if atc and atc.startswith("J01C"):
            return "Пенициллины"
        return None

    def resolve_diagnosis(self, diagnosis: str | None, icd10: str | None) -> list[str]:
        """P1-B: returns guideline_ids via normalization (delegates to normalize + but ids via caller).
        Kept for compat; main work in normalize_diagnosis + stage lookup."""
        # For backward, return empty; actual ids come from enhanced lookup in DiagnosisMatch
        return []

    def normalize_diagnosis(self, diagnosis: str | None, icd10: str | None) -> DiagnosisNormalization | None:
        """P1-B core: produce normalized forms + full traceable explanation.
        Used by stages to improve lookup accuracy and satisfy Clinical Traceability Rule.
        Simple rule-based confidence. No ML.
        """
        orig_d = diagnosis
        orig_i = icd10
        norm_d: str | None = None
        norm_i: str | None = None
        syn_used: str | None = None
        icd_map: str | None = None
        conf = "LOW"
        reasons: list[str] = []

        if diagnosis:
            key = diagnosis.strip().lower()
            if key in self._diagnosis_synonyms:
                norm_d = self._diagnosis_synonyms[key]
                syn_used = f"{diagnosis} → {norm_d}"
                reasons.append("synonym")

        if icd10:
            ni = self._normalize_icd(icd10)
            up = icd10.strip().upper()
            if ni and ni != up:
                norm_i = ni
                icd_map = f"{icd10} → {ni}"
                reasons.append("icd_norm")
            else:
                norm_i = up

        if not norm_d:
            norm_d = diagnosis  # pass-through if no synonym
        if not norm_i and icd10:
            norm_i = self._normalize_icd(icd10) or icd10.strip().upper()

        if syn_used and icd_map:
            conf = "HIGH"
        elif syn_used or icd_map:
            conf = "MEDIUM"
        else:
            conf = "LOW"

        reason = " + ".join(reasons) if reasons else "exact or pass-through"
        source = "diagnosis_synonyms.json + _normalize_icd"

        return DiagnosisNormalization(
            original_diagnosis=orig_d,
            original_icd=orig_i,
            normalized_diagnosis=norm_d,
            normalized_icd=norm_i,
            synonym_used=syn_used,
            icd_mapping=icd_map,
            confidence=conf,
            reason=reason,
            source=source,
        )

    @staticmethod
    def _normalize_icd(icd: str | None) -> str | None:
        """Simple ICD-10 normalization for lookup match.
        J01.0 / J01.00 / j01 → J01
        Keeps base code as stored in index.
        """
        if not icd:
            return None
        s = icd.strip().upper()
        if "." in s:
            s = s.split(".")[0]
        # For codes like J01 keep as is; for longer take prefix if needed (index uses 3-char mostly)
        return s

    def get_mapping(self, drug_ref: str) -> TerminologyMapping | None:
        """For trace: source of decision."""
        atc = self.get_atc(drug_ref)
        if atc:
            return TerminologyMapping("drug_atc", drug_ref, atc)
        cls = self.get_allergy_class(drug_ref)
        if cls:
            return TerminologyMapping("allergy_class_map", drug_ref, cls)
        return None
