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
    def get_allergy_class(self, drug_ref: str, drug_class: str | None = None) -> str | None: ...
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


# ---------------------------------------------------------------------------
# Allergy class resolution (M-4)
#
# `allergy_class_hierarchy` used to be loaded and never read. It is the
# authoritative class vocabulary: `allergy_class_map` is exactly its reverse
# index in production, so resolving through the hierarchy instead of the map
# is behaviour-preserving there -- and lets us close the gap where 7 drugs in
# db/index.json (tobramycin, netilmicin, ofloxacin, tetracycline, tinidazole,
# rifaximin, furazidin) appear in NEITHER map, so every allergic patient got
# a useless ALLERGY_UNVERIFIABLE for them.
#
# The hierarchy's keys are drug-family names ("Пенициллины"); db/index.json's
# per-drug `class` field is the detailed label of the same family
# ("Полусинтетические пенициллины широкого спектра"). Matching a label to its
# family is what turns "the patient is allergic to Пенициллины" into an
# exclusion for amoxicillin, instead of a string comparison between two
# spellings of the same fact.
# ---------------------------------------------------------------------------

# Documented class-label families that share a family name with no member of
# the curated hierarchy. Kept explicit (no fuzzy guessing): "Производные
# имидазола" are 5-nitroimidazoles, the family metronidazole belongs to.
_CLASS_LABEL_ALIASES: dict[str, str] = {
    "Производные имидазола": "Нитроимидазолы",
}

# Cross-reactivity: a documented, non-absolute risk. Allergy to one family
# raises a WARNING on the other -- it never excludes, because the real-world
# risk is a minority of patients and a first/second-generation cephalosporin
# shares no side chain with most penicillins.
#   - penicillin <-> cephalosporin: ~1-10% clinically significant cross-
#     reactivity overall, higher for early-generation cephalosporins whose
#     side chain resembles an aminothiazole penicillin side chain.
_CROSS_REACTIVE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"Пенициллины", "Цефалоспорины"}),
)


def _norm_class(value: str | None) -> str:
    """Casefolded, whitespace-collapsed class name for comparison."""
    return " ".join((value or "").split()).casefold()


def _class_name_variants(value: str | None) -> tuple[str, str]:
    """(normalized full name, first word) for a class name or label."""
    norm = _norm_class(value)
    return norm, norm.split(" ", 1)[0] if norm else ""


@dataclass(frozen=True, slots=True)
class AllergyClassResolution:
    """Resolved allergy class + WHERE it came from (Clinical Traceability)."""

    class_name: str | None
    source: str  # allergy_class_map | allergy_class_hierarchy | drug_class_label
                    # | drug_class_alias | atc | unresolved


class AllergyClassResolver:
    """Resolves a drug_ref (and its own class label) to a canonical family.

    Resolution order, first hit wins:
      1. ``allergy_class_map[drug_ref]``          -- curated per-drug class
      2. ``allergy_class_hierarchy`` reverse index -- curated family of the drug
      3. the drug's own ``class`` label vs the family vocabulary
         (exact / whole-word / unambiguous family head-word)
      4. documented label aliases
      5. ATC prefix fallback (``J01C*`` -> Пенициллины), only when an ATC map
         is supplied (the terminology binding path)
    """

    def __init__(self, constants: ClinicalConstants) -> None:
        self._class_by_ref: dict[str, str] = dict(constants.allergy_class_map)
        self._family_by_ref: dict[str, str] = {}
        for family, members in (constants.allergy_class_hierarchy or {}).items():
            for member in members:
                self._family_by_ref.setdefault(member, family)
        self._families: tuple[str, ...] = tuple(
            dict.fromkeys(
                list((constants.allergy_class_hierarchy or {}).keys())
                + list(self._class_by_ref.values())
            )
        )
        self._family_by_norm: dict[str, str] = {}
        self._family_by_head: dict[str, str] = {}
        head_counts: dict[str, int] = {}
        for family in self._families:
            self._family_by_norm.setdefault(_norm_class(family), family)
            _, head = _class_name_variants(family)
            if head:
                head_counts[head] = head_counts.get(head, 0) + 1
        for family in self._families:
            _, head = _class_name_variants(family)
            # Only unambiguous head words ("Ансамицины" -> the single
            # "Ансамицины (...)" family). "Пенициллины" heads three families
            # and is therefore never resolved this way.
            if head and head_counts.get(head) == 1:
                self._family_by_head.setdefault(head, family)

    # -- drug side --------------------------------------------------
    def resolve(
        self,
        drug_ref: str | None,
        drug_class: str | None = None,
        atc: str | None = None,
    ) -> AllergyClassResolution:
        if drug_ref:
            curated = self._class_by_ref.get(drug_ref) or self._family_by_ref.get(drug_ref)
            if curated:
                source = (
                    "allergy_class_map" if drug_ref in self._class_by_ref
                    else "allergy_class_hierarchy"
                )
                return AllergyClassResolution(curated, source)
        if drug_class:
            family = self._family_for_label(drug_class)
            if family:
                return AllergyClassResolution(
                    family, "drug_class_alias" if family in _CLASS_LABEL_ALIASES.values()
                    else "drug_class_label"
                )
        if atc and atc.upper().startswith("J01C"):
            return AllergyClassResolution("Пенициллины", "atc")
        return AllergyClassResolution(None, "unresolved")

    def _family_for_label(self, label: str) -> str | None:
        norm = _norm_class(label)
        if not norm:
            return None
        alias = _CLASS_LABEL_ALIASES.get(label.strip()) or _CLASS_LABEL_ALIASES.get(
            " ".join(label.split())
        )
        if alias:
            return alias
        exact = self._family_by_norm.get(norm)
        if exact:
            return exact
        # Whole-word containment either way: a family name is a whole word
        # inside the label ("Пенициллины" inside "Полусинтетические
        # пенициллины широкого спектра"), or the label's own words are covered
        # by a family name.
        for family_norm, family in self._family_by_norm.items():
            if _whole_word_in(family_norm, norm) or _whole_word_in(norm, family_norm):
                return family
        _, head = _class_name_variants(label)
        if head:
            return self._family_by_head.get(head)
        return None

    # -- patient side -----------------------------------------------
    def canonical_family(self, stated: str) -> str | None:
        """Map a physician-stated allergy onto a canonical family name.

        Returns the family, or the input unchanged when it matches no known
        family (an unrecognised allergy must still be compared verbatim, not
        dropped).
        """
        family = self._family_for_label(stated)
        return family if family else stated.strip()

    def cross_reactive_with(self, family: str | None) -> tuple[str, ...]:
        """Families documented as cross-reactive with `family`."""
        if not family:
            return ()
        target = _norm_class(family)
        out: list[str] = []
        for pair in _CROSS_REACTIVE_FAMILIES:
            if target in {_norm_class(f) for f in pair}:
                out.extend(sorted(f for f in pair if _norm_class(f) != target))
        return tuple(dict.fromkeys(out))


def _whole_word_in(needle: str, haystack: str) -> bool:
    """True when `needle` appears in `haystack` delimited by word boundaries."""
    if not needle or not haystack:
        return False
    idx = haystack.find(needle)
    while idx != -1:
        before_ok = idx == 0 or not haystack[idx - 1].isalnum()
        end = idx + len(needle)
        after_ok = end == len(haystack) or not haystack[end].isalnum()
        if before_ok and after_ok:
            return True
        idx = haystack.find(needle, idx + 1)
    return False



class BasicTerminologyProvider:
    """Current impl. Additive. Uses constants map + class hierarchy."""

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
        # L-6: a real lookup map must never be seeded with a synthetic entry.
        # "unmapped_pen" -> "J01CA04" was a P1 demo value that made the engine
        # return a confident ATC code for a drug that has none; an unmapped
        # drug now resolves to None and the caller degrades (ALLERGY_UNVERIFIABLE).
        self._allergy_resolver = AllergyClassResolver(constants)

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

    @property
    def allergy_resolver(self) -> AllergyClassResolver:
        return self._allergy_resolver

    def get_atc(self, drug_ref: str) -> str | None:
        if not drug_ref:
            return None
        return self._atc_map.get(drug_ref.lower())

    def get_allergy_class(self, drug_ref: str, drug_class: str | None = None) -> str | None:
        if not drug_ref:
            return None
        return self.resolve_allergy_class(drug_ref, drug_class).class_name

    def resolve_allergy_class(
        self, drug_ref: str, drug_class: str | None = None
    ) -> AllergyClassResolution:
        """Full resolution incl. the ATC fallback and its provenance source."""
        return self._allergy_resolver.resolve(
            drug_ref, drug_class, atc=self.get_atc(drug_ref) if drug_ref else None
        )

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
        res = self.resolve_allergy_class(drug_ref)
        if res.class_name:
            return TerminologyMapping(res.source, drug_ref, res.class_name)
        return None
