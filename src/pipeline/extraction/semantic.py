"""Medical Semantic Layer for P4.3.

Medical NER + Normalization + Clinical Semantics.
Lightweight. Dict + regex + medical_normalizer. No heavy new deps.
All entities normalized. Structured objects + relations + quality + consistency.
Real execution verified. No frozen Clinical Engine touch.
"""

import os
import re
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

# Optional external site-packages directory for heavyweight extraction deps
# (transformers) when they live outside the active environment. Opt-in only
# via ANTIBIO_EXTERNAL_SITE_PACKAGES — never a hard-coded, machine-specific
# path. See .env.example.
_external_site_packages = os.environ.get("ANTIBIO_EXTERNAL_SITE_PACKAGES", "").strip()
if _external_site_packages:
    if not os.path.isdir(_external_site_packages):
        raise RuntimeError(
            "ANTIBIO_EXTERNAL_SITE_PACKAGES is set but does not point to an "
            f"existing directory: {_external_site_packages!r}"
        )
    if _external_site_packages not in sys.path:
        sys.path.insert(0, _external_site_packages)

try:
    from transformers import pipeline
except ImportError:
    pipeline = None

from .base import Document, Page

# === Load dicts (existing medical_dictionary, no install) ===
#
# H-11: all eight loads were individually wrapped in `except Exception: return {}`
# or a bare except assigning empty dicts.  A missing or malformed
# medical_dictionary/ therefore let the pipeline run to COMPLETION producing ZERO
# Medication objects and zero Route/Frequency/Duration entities, recorded only in
# metadata["normalization_rate"] -- which nothing inspects.  That is a fail-open on
# the single most safety-relevant dependency in the extraction stack.  Loads now
# fail loudly: a missing file or malformed JSON raises, and an empty
# safety-relevant dictionary raises too.
class MedicalDictionaryUnavailable(RuntimeError):
    """The medical dictionary is missing, malformed, or empty."""


_DICTIONARY_ROOT = Path(__file__).resolve().parents[3] / "medical_dictionary"
# The only legitimate fallback is the current working directory, and it is checked
# AFTER the package-relative path so the result cannot depend on where pytest or
# the CLI happened to be launched (L-22).
_DICTIONARY_FALLBACK_ROOT = Path("medical_dictionary")


def _dictionary_root() -> Path:
    if _DICTIONARY_ROOT.is_dir():
        return _DICTIONARY_ROOT
    if _DICTIONARY_FALLBACK_ROOT.is_dir():
        return _DICTIONARY_FALLBACK_ROOT
    raise MedicalDictionaryUnavailable(
        f"medical_dictionary/ not found (looked in {_DICTIONARY_ROOT} and "
        f"{_DICTIONARY_FALLBACK_ROOT.absolute()})"
    )


def _load_json_safe(name: str) -> Dict[str, Any]:
    """Load one dictionary file, failing loudly on absence or malformation."""
    path = _dictionary_root() / name
    if not path.is_file():
        raise MedicalDictionaryUnavailable(f"required dictionary file missing: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise MedicalDictionaryUnavailable(f"malformed dictionary file {path}: {exc}") from exc
    if isinstance(data, dict):
        return data.get("entries", data)
    return data


def _require_non_empty(name: str, mapping: Any) -> Dict[str, Any]:
    if not isinstance(mapping, dict) or not mapping:
        raise MedicalDictionaryUnavailable(
            f"dictionary {name!r} is empty; extraction would silently produce zero "
            f"entities of this kind, which is a fail-open, not a valid result"
        )
    return mapping


try:
    from medical_dictionary.loader import (
        load_drug_synonyms, load_drug_atc, load_route_synonyms, load_unit_normalization,
        load_drug_groups
    )
    # Only the three dictionaries whose absence would change CLINICAL SAFETY are
    # required to be non-empty: without drug synonyms no Medication is extracted at
    # all, without route synonyms no Route entity, without unit normalization no
    # dose carries a unit.  drug_atc / drug_groups are legitimately empty in this
    # corpus (the project tracks them as pending review); their absence costs
    # recall, not safety, so their size is reported instead of enforced.
    DRUG_SYNONYMS = _require_non_empty("drug_synonyms", load_drug_synonyms())
    ROUTE_SYN = _require_non_empty("route_synonyms", load_route_synonyms())
    UNIT_NORM = _require_non_empty("unit_normalization", load_unit_normalization())
    DRUG_ATC = load_drug_atc() or {}
    DRUG_GROUPS = load_drug_groups() or {}
except MedicalDictionaryUnavailable:
    raise
except Exception as exc:
    raise MedicalDictionaryUnavailable(
        f"medical_dictionary.loader failed: {type(exc).__name__}: {exc}"
    ) from exc

DICTIONARY_SIZES = {
    "drug_synonyms": len(DRUG_SYNONYMS),
    "drug_atc": len(DRUG_ATC),
    "drug_groups": len(DRUG_GROUPS),
    "route_synonyms": len(ROUTE_SYN),
    "unit_normalization": len(UNIT_NORM),
}

DIAG_SYN = _load_json_safe("diagnosis_synonyms.json")
FREQ_DICT = _load_json_safe("frequency_dictionary.json")
DUR_DICT = _load_json_safe("duration_dictionary.json")
PREG_DICT = _load_json_safe("pregnancy_dictionary.json")
RENAL_DICT = _load_json_safe("renal_dictionary.json")

# Try normalizer for canonical formats (reuse proven).  A missing normalizer is NOT
# fatal (the dict path still works), but it is recorded so the degradation is visible
# rather than invisible.
NORMALIZER: Any = None
_NORMALIZER_ERROR: str | None = None
try:
    from medical_normalizer.normalizer import MedicalNormalizer
    NORMALIZER = MedicalNormalizer()
except Exception as exc:  # noqa: BLE001 - degradation must be reported, not hidden
    _NORMALIZER_ERROR = f"{type(exc).__name__}: {exc}"
    print(f"[Semantic] MedicalNormalizer unavailable ({_NORMALIZER_ERROR}) — "
          f"dictionary path only, clinical_normalizer='unavailable'")

# M-16: the flat-text and table-cell paths iterated DIFFERENT slices of the same
# dictionary (:500 vs :200), so the two paths could extract from different
# vocabularies for the same page.  One shared bound, applied identically.
DRUG_SYNONYM_SCAN_LIMIT = 500

# M-17: dedup truncated at 60 characters in one place and 50 in another, so an
# entity with a 51..60 character surface form was added twice.  One shared width.
ENTITY_DEDUP_KEY_LENGTH = 60

# H-10: Frequency/Duration/Route were appended to the `Dose` bucket with
# unit=None, so `SELECT * FROM objects WHERE type='Dose'` returned rows whose value
# was "3_times_daily" and knowledge_invariants INV-05 ("Every Dose has a unit")
# could not see them.  They now have their own types.
_DOSE_OWNED_TYPES = ("Dose", "Frequency", "Duration", "Route")

# H-12: how close two entities must be in the source text for a relation between
# them to be evidence-backed rather than fabricated.  400 characters is roughly the
# length of a guideline sentence pair, so a dose must sit in the same prescription
# block as the diagnosis it is attached to.
RELATION_PROXIMITY_CHARS = 400

# Which knowledge-object type a relation's `to` endpoint must belong to.  H-12:
# `check_consistency` never validated that a relation's endpoints were even
# semantically compatible, so anything could be linked to anything.
_RELATION_TARGET_TYPE = {
    "first_line": ("Drug", "FirstLineTherapy"),
    "dose": ("Dose",),
    "frequency": ("Frequency",),
    "duration": ("Duration",),
    "contraindication": ("Contraindication", "Pregnancy", "Breastfeeding", "RenalAdjustment"),
    "alternative": ("AlternativeTherapy",),
}

# Entity types (STEP 4 min support)
ENTITY_TYPES = [
    "Drug", "DrugClass", "ATC", "Diagnosis", "ICD-10",
    "Dose", "DoseUnit", "Frequency", "Duration", "Route",
    "AgeRestriction", "Pregnancy", "Breastfeeding", "RenalAdjustment",
    "Contraindication", "AlternativeTherapy", "FirstLineTherapy",
    "StrengthOfRecommendation", "EvidenceLevel", "SourceReference"
]

def _relation_endpoints_compatible(rel: Dict[str, Any]) -> bool:
    """H-12: reject a relation whose endpoints are not semantically compatible.

    ``extract_relations`` records the normalized VALUE as the target, so the target
    entity TYPE is carried alongside it in ``to_type``.  A ``dose`` relation whose
    target is a Route is nonsense, and it used to be persisted anyway.
    """
    allowed = _RELATION_TARGET_TYPE.get(rel.get("rel"))
    if allowed is None:
        return False
    if not rel.get("to") or not rel.get("from"):
        return False
    if rel.get("to_type") not in allowed:
        return False
    return True


class SemanticProcessor:
    """Production semantic. Dict primary. Regex + normalizer. Real only."""

    def __init__(self):
        self.ner = None
        self.ner_error: Optional[str] = None
        # NER optional, general not medical-specific. Justify: use domain dicts (proven in normalizer 823 tests). No download heavy model for CPU prod.
        self._load_ner_optional()

    def _load_ner_optional(self):
        """Load the optional generic NER model.

        L-24: the bare ``except: self.ner = None`` was explicitly annotated
        "silent, not justified" -- i.e. the author knew it was unjustified.  The
        failure is now REPORTED and recorded on the instance, so a degraded run is
        visible instead of looking like a domain decision.  Disabling remains the
        right behaviour: this generic model is not a medical NER and the domain
        dictionaries are the primary path.
        """
        if pipeline is None:
            self.ner_error = "transformers not installed"
            return
        try:
            self.ner = pipeline("ner", model="Babelscape/wikineural-multilingual-ner",
                                aggregation_strategy="simple", device=-1)
        except Exception as exc:  # noqa: BLE001
            self.ner = None
            self.ner_error = f"{type(exc).__name__}: {exc}"
            print(f"[Semantic] optional NER model unavailable ({self.ner_error}) — "
                  f"relying on domain dictionaries")

    def extract_entities(self, text: str, page_num: int = 0, engine: str = "unknown") -> List[Dict[str, Any]]:
        if not text:
            return []
        entities: List[Dict[str, Any]] = []
        tlow = text.lower()

        # Dict drugs (high conf)
        for syn, can in list(DRUG_SYNONYMS.items())[:DRUG_SYNONYM_SCAN_LIMIT]:
            if syn and syn.lower() in tlow:
                entities.append(self._mk_ent("Drug", syn, can, 0.92, page_num, engine, "dict_drug"))

        # ATC (if present)
        for drug, atc in DRUG_ATC.items():
            if drug.lower() in tlow and atc:
                entities.append(self._mk_ent("ATC", atc, atc, 0.85, page_num, engine, "dict_atc"))

        # Diagnosis
        for k, v in (DIAG_SYN if isinstance(DIAG_SYN, dict) else {}).items():
            if str(k).lower() in tlow:
                entities.append(self._mk_ent("Diagnosis", str(k), str(v), 0.88, page_num, engine, "dict_diag"))

        # ICD rough
        # L-23: the class was [a-z] under re.I, which also matches Cyrillic
        # homoglyphs, and `10?` made "icd-1" a valid prefix.
        icd_re = re.compile(
            r'(?:мкб|icd[\s-]?10)(?![0-9])[\s]*[:\-]?[\s]*([A-Za-z]\d{2}(?:\.\d{1,4})?)',
            re.IGNORECASE,
        )
        for m in icd_re.finditer(text):
            entities.append(self._mk_ent("ICD-10", m.group(0), m.group(1).upper(), 0.8, page_num, engine, "regex_icd"))

        # Dose + unit (enhanced regex + norm)
        dose_re = r'(\d+[\.,]?\d*)\s*(мг|г|мл|мкг|доз|таб|капс|ед|ме|мг/кг)'
        for m in re.finditer(dose_re, text, re.I):
            unit_raw = m.group(2)
            unit = UNIT_NORM.get(unit_raw.lower(), unit_raw)
            norm_val = m.group(1).replace(",", ".")
            entities.append({
                "type": "Dose", "text": m.group(0), "normalized": norm_val,
                "unit": unit, "confidence": 0.85,
                "provenance": {"page": page_num, "extractor": engine, "source": "regex_dose", "norm_status": "unit_mapped" if unit != unit_raw else "raw"}
            })

        # Frequency
        for pat, can in (FREQ_DICT.items() if isinstance(FREQ_DICT, dict) else []):
            if str(pat).lower() in tlow:
                entities.append(self._mk_ent("Frequency", str(pat), str(can), 0.87, page_num, engine, "dict_freq"))

        # Duration
        for pat, can in (DUR_DICT.items() if isinstance(DUR_DICT, dict) else []):
            if str(pat).lower() in tlow:
                entities.append(self._mk_ent("Duration", str(pat), str(can), 0.86, page_num, engine, "dict_dur"))

        # Route
        for syn, can in ROUTE_SYN.items():
            if syn.lower() in tlow:
                entities.append(self._mk_ent("Route", syn, can, 0.9, page_num, engine, "dict_route"))

        # Pregnancy / Breastfeeding / Renal (special pop)
        for syn, can in (PREG_DICT.items() if isinstance(PREG_DICT, dict) else []):
            if str(syn).lower() in tlow:
                entities.append(self._mk_ent("Pregnancy", str(syn), str(can), 0.89, page_num, engine, "dict_preg"))
        # Breastfeeding rough
        if any(x in tlow for x in ["грудн", "лактац", "breastfeeding"]):
            entities.append(self._mk_ent("Breastfeeding", "лактация", "contraindicated_or_caution", 0.7, page_num, engine, "rule"))
        for syn, can in (RENAL_DICT.items() if isinstance(RENAL_DICT, dict) else []):
            if str(syn).lower() in tlow:
                entities.append(self._mk_ent("RenalAdjustment", str(syn), str(can), 0.88, page_num, engine, "dict_renal"))

        # Contraindication / Alt / First line rough keywords
        if "противопоказан" in tlow or "противопоказания" in tlow:
            entities.append(self._mk_ent("Contraindication", "противопоказан", "contraindicated", 0.75, page_num, engine, "keyword"))
        if "альтернатив" in tlow or "альтернативн" in tlow:
            entities.append(self._mk_ent("AlternativeTherapy", "альтернатива", "alternative", 0.72, page_num, engine, "keyword"))
        if "препарат выбора" in tlow or "первая линия" in tlow or "first line" in tlow:
            entities.append(self._mk_ent("FirstLineTherapy", "препарат выбора", "first_line", 0.78, page_num, engine, "keyword"))

        # Evidence / strength rough
        if "уровень доказательств" in tlow or "evidence" in tlow:
            entities.append(self._mk_ent("EvidenceLevel", "уровень доказательств", "extracted", 0.65, page_num, engine, "keyword"))
        if "рекомендац" in tlow and ("сильн" in tlow or "слаб" in tlow or "strong" in tlow):
            entities.append(self._mk_ent("StrengthOfRecommendation", "рекомендация", "extracted", 0.65, page_num, engine, "keyword"))

        # Source ref rough (guideline mention)
        for m in re.finditer(r'(клиническ[ие] рекомендац|КР|guideline|МЗ РФ)', text, re.I):
            entities.append(self._mk_ent("SourceReference", m.group(0), "MoH_RU", 0.6, page_num, engine, "keyword"))

        # Dedup + quality
        seen = set()
        unique = []
        for e in entities:
            key = (e["type"], e.get("text", "").lower()[:ENTITY_DEDUP_KEY_LENGTH])
            if key not in seen:
                seen.add(key)
                e.setdefault("confidence", 0.7)
                e.setdefault("normalization_status", e.get("provenance", {}).get("norm_status", "dict_mapped" if "dict" in str(e.get("provenance", {})) else "raw"))
                unique.append(e)
        return unique

    def _mk_ent(self, typ: str, text: str, norm: str, conf: float, page: int, engine: str, src: str) -> Dict[str, Any]:
        return {
            "type": typ, "text": text, "normalized": norm,
            "confidence": conf,
            # H-8: the producer wrote the per-entity extractor under `engine` while
            # Provenance names the field `extractor`, so the consumer always read
            # None and fell back to the document-level source.  Write the canonical
            # name; the consumer still accepts `engine` for legacy rows.
            "provenance": {"page": page, "extractor": engine, "source": src, "coordinates": None},
            "normalization_status": "dict_mapped" if "dict" in src else "raw"
        }

    def extract_relations(self, text: str, entities: List[Dict]) -> List[Dict[str, Any]]:
        """STEP 7: clinical relations, restricted to what the text actually supports.

        H-12: the old loop linked EVERY diagnosis on a page to EVERY dose
        (``for d in diags[:3]: for ds in doses[:2]``), so a page with 3 diagnoses
        and 2 doses emitted 6 `dose` relations, most of them clinically wrong, and
        they were persisted.  Nothing ever checked that a relation's endpoints were
        even semantically compatible.

        A relation is emitted only when there is POSITIONAL evidence: the two
        entities occur within :data:`RELATION_PROXIMITY_CHARS` characters of each
        other in the source text, and the nearest candidate wins.  Endpoints are
        validated by :func:`_relation_endpoints_compatible`.
        """
        rels: List[Dict[str, Any]] = []
        diags = [e for e in entities if e["type"] == "Diagnosis"]
        drugs = [e for e in entities if e["type"] == "Drug"]
        doses = [e for e in entities if e["type"] == "Dose"]
        freqs = [e for e in entities if e["type"] == "Frequency"]
        durs = [e for e in entities if e["type"] == "Duration"]
        alts = [e for e in entities if e["type"] == "AlternativeTherapy"]
        contras = [e for e in entities if e["type"] == "Contraindication"]
        firsts = [e for e in entities if e["type"] == "FirstLineTherapy"]

        haystack = (text or "").lower()

        def _nearest(anchor: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            anchor_pos = haystack.find(str(anchor.get("text", "")).lower())
            if anchor_pos < 0:
                return []
            scored: List[tuple[int, Dict[str, Any]]] = []
            for candidate in candidates:
                pos = haystack.find(str(candidate.get("text", "")).lower())
                if pos < 0:
                    continue
                distance = abs(pos - anchor_pos)
                if distance <= RELATION_PROXIMITY_CHARS:
                    scored.append((distance, candidate))
            scored.sort(key=lambda pair: pair[0])
            return [candidate for _distance, candidate in scored]

        for d in diags[:3]:
            for f in _nearest(d, firsts or drugs)[:1]:
                rels.append({"from": d["normalized"], "rel": "first_line", "from_type": "Diagnosis",
                             "to": f["normalized"], "to_type": f["type"], "confidence": 0.6})
            for ds in _nearest(d, doses)[:1]:
                rels.append({"from": d["normalized"] or "dx", "rel": "dose", "from_type": "Diagnosis",
                             "to": ds["normalized"] + (ds.get("unit") or ""), "to_type": "Dose",
                             "confidence": 0.65})
            for fr in _nearest(d, freqs)[:1]:
                rels.append({"from": d.get("normalized", "dx"), "rel": "frequency", "from_type": "Diagnosis",
                             "to": fr["normalized"], "to_type": "Frequency", "confidence": 0.6})
            for du in _nearest(d, durs)[:1]:
                rels.append({"from": d.get("normalized", "dx"), "rel": "duration", "from_type": "Diagnosis",
                             "to": du["normalized"], "to_type": "Duration", "confidence": 0.6})
        for c in contras:
            rels.append({"from": "population", "rel": "contraindication", "from_type": "Population",
                         "to": c["normalized"], "to_type": c["type"], "confidence": 0.7})
        for a in alts[:2]:
            rels.append({"from": "therapy", "rel": "alternative", "from_type": "Therapy",
                         "to": a["normalized"], "to_type": "AlternativeTherapy", "confidence": 0.6})
        return [r for r in rels if _relation_endpoints_compatible(r)][:15]

    def build_knowledge_objects(self, entities: List[Dict]) -> Dict[str, List[Dict]]:
        """P4.4 + P4.5: Rich Knowledge Objects with full lineage (table cell provenance).

        H-10: ``Dose``, ``Frequency``, ``Duration`` and ``Route`` were ALL appended to
        the ``Dose`` bucket with ``unit=None``, so
        ``SELECT * FROM objects WHERE type='Dose'`` returned rows whose value was
        ``"3_times_daily"`` — and ``knowledge_invariants.INV-05`` ("Every Dose has a
        unit") was ``advisory_ok=True`` so it could never block CI anyway.  Each type
        now lands in its own bucket, and only a genuine ``Dose`` has to carry a unit.
        """
        objs: Dict[str, List[Dict]] = {
            "Medication": [], "Diagnosis": [], "Dose": [], "Contraindication": [],
            "Recommendation": [], "Evidence": [],
            "Frequency": [], "Duration": [], "Route": [],
        }

        for e in entities:
            prov = dict(e.get("provenance", {}) or {})
            # PROVENANCE_SPECIFICATION v2: stamp per-entity original wording + normalized value onto
            # the provenance dict under canonical keys, so the consumer maps them 1:1 (fixes RC-012:
            # original_text was lost because the KB read a different key than the builder wrote).
            prov.setdefault("original_text", e.get("text"))
            prov.setdefault("normalized_value", e.get("normalized"))
            prov.setdefault("semantic_engine", prov.get("semantic_engine", "semantic.py"))
            base = {
                "raw": e.get("text"),
                "normalized": e.get("normalized"),
                "confidence": e.get("confidence", 0.7),
                "provenance": prov,   # canonical keys: row/col/bbox/extractor/original_text/normalized_value
                "normalization_status": e.get("normalization_status", "raw"),
            }

            if e["type"] == "Drug":
                base.update({"name": e.get("normalized") or e.get("text")})
                objs["Medication"].append(base)

            elif e["type"] == "Diagnosis":
                base.update({"name": e.get("normalized") or e.get("text")})
                objs["Diagnosis"].append(base)

            elif e["type"] == "Dose":
                # Only a genuine dose carries a `unit`; a dose with no unit is
                # incomplete and is visible as such.
                base.update({"value": e.get("normalized"), "unit": e.get("unit")})
                objs["Dose"].append(base)

            elif e["type"] in ("Frequency", "Duration", "Route"):
                base.update({
                    "value": e.get("normalized"),
                    "unit": e.get("unit"),
                    "subtype": e["type"],
                })
                objs[e["type"]].append(base)

            elif e["type"] in ("Contraindication", "Pregnancy", "Breastfeeding", "RenalAdjustment"):
                base.update({"condition": e.get("normalized") or e.get("text"), "subtype": e["type"]})
                objs["Contraindication"].append(base)

            elif e["type"] in ("EvidenceLevel", "StrengthOfRecommendation", "SourceReference"):
                base.update({"level": e.get("normalized"), "subtype": e["type"]})
                objs["Evidence"].append(base)

            elif e["type"] in ("FirstLineTherapy", "AlternativeTherapy"):
                base.update({"therapy": e.get("normalized") or e.get("text"), "line": e["type"]})
                objs["Recommendation"].append(base)

        return objs

    def check_consistency(self, entities: List[Dict], relations: List[Dict]) -> List[str]:
        """STEP 9: auto validation. dups, format, missing, orphan."""
        warns = []
        seen = {}
        for e in entities:
            k = (e["type"], e.get("text", "")[:40].lower())
            if k in seen:
                warns.append(f"duplicate_{e['type']}: {e['text']}")
            seen[k] = True
        # missing unit on dose
        for e in entities:
            if e["type"] == "Dose" and not e.get("unit"):
                warns.append("missing_unit_dose")
            if e["type"] == "Dose" and not e.get("normalized"):
                warns.append("invalid_dose_format")
        # unresolved norm
        for e in entities:
            if e.get("normalization_status") == "raw" and e["type"] in ("Drug", "Diagnosis"):
                warns.append(f"unresolved_norm_{e['type']}")
        # H-12: relation endpoints must be semantically compatible.
        for rel in relations:
            if not _relation_endpoints_compatible(rel):
                warns.append(f"incompatible_relation_endpoints: {rel.get('rel')}")
        # orphan: entity no relation rough
        if entities and not relations:
            warns.append("orphan_entities")
        # contradictory rough
        has_first = any(e["type"] == "FirstLineTherapy" for e in entities)
        has_alt = any(e["type"] == "AlternativeTherapy" for e in entities)
        if has_first and has_alt and len(entities) < 3:
            warns.append("contradictory_recs_possible")
        # M-18: `list(set(...))[:10]` was non-deterministic between runs
        # (PYTHONHASHSEED), breaking reproducibility of hash-pinned artifacts.
        return sorted(set(warns))[:10]

    def extract_entities_from_tables(self, structured_tables: List[Any], page_num: int = 0, engine: str = "layout+table") -> List[Dict[str, Any]]:
        """P4.5: Consume structured TableObjects / cells for higher-fidelity regimen facts.

        Cells often contain the authoritative dose, frequency, duration, alternatives, peds strat.
        Attaches cell provenance (row, col, bbox) for full traceability.
        """
        entities: List[Dict[str, Any]] = []
        if not structured_tables:
            return entities

        for tbl in structured_tables:
            for cell in getattr(tbl, "cells", []):
                txt = (cell.text or "").strip()
                if not txt or len(txt) < 3:
                    continue
                tlow = txt.lower()
                # PROVENANCE_SPECIFICATION v2: canonical keys (Provenance field names). The consumer
                # maps 1:1 and never infers engines from `source`.
                prov = {
                    "page": getattr(cell, "page_num", page_num),
                    "layout_engine": getattr(tbl, "engine", "table-transformer+rapidtable"),
                    "semantic_engine": "semantic+table",
                    "source": "table_cell",
                    "table_row": cell.row,
                    "table_col": cell.col,
                    "bounding_box": getattr(cell.bbox, "__dict__", None) if cell.bbox else None,
                    "table_conf": getattr(tbl, "confidence", 0.0),
                }

                # Drug / dose in cell (very high value for regimens)
                for syn, can in list(DRUG_SYNONYMS.items())[:DRUG_SYNONYM_SCAN_LIMIT]:
                    if syn and syn.lower() in tlow:
                        e = self._mk_ent("Drug", syn, can, 0.94, page_num, engine, "table_dict_drug")
                        e["provenance"].update(prov)
                        entities.append(e)

                # Dose patterns inside cell
                dose_re = r'(\d+[\.,]?\d*)\s*(мг|г|мл|мг/кг|МЕ)'
                for m in re.finditer(dose_re, txt, re.I):
                    unit = UNIT_NORM.get(m.group(2).lower(), m.group(2))
                    entities.append({
                        "type": "Dose", "text": m.group(0), "normalized": m.group(1).replace(",", "."),
                        "unit": unit, "confidence": 0.91,
                        "provenance": {**prov, "source": "table_cell_dose"}
                    })

                # Duration / frequency / route in cell
                for pat, can in (FREQ_DICT.items() if isinstance(FREQ_DICT, dict) else []):
                    if str(pat).lower() in tlow:
                        e = self._mk_ent("Frequency", str(pat), str(can), 0.88, page_num, engine, "table_dict_freq")
                        e["provenance"].update(prov)
                        entities.append(e)

                for pat, can in (DUR_DICT.items() if isinstance(DUR_DICT, dict) else []):
                    if str(pat).lower() in tlow:
                        e = self._mk_ent("Duration", str(pat), str(can), 0.87, page_num, engine, "table_dict_dur")
                        e["provenance"].update(prov)
                        entities.append(e)

                # Alternative / first line indicators in table cells
                if "альтернатив" in tlow:
                    entities.append({"type": "AlternativeTherapy", "text": txt[:80], "normalized": "alternative",
                                     "confidence": 0.78, "provenance": {**prov, "source": "table_cell"}})
                if any(x in tlow for x in ["первой линии", "препарат выбора", "рекомендуется"]):
                    entities.append({"type": "FirstLineTherapy", "text": txt[:80], "normalized": "first_line",
                                     "confidence": 0.8, "provenance": {**prov, "source": "table_cell"}})

                # Pediatric / weight stratification (key from audit)
                if any(x in tlow for x in ["мг/кг", "масса", "вес", "кг", "0-7", "8-28"]):
                    entities.append({"type": "AgeRestriction", "text": txt[:100], "normalized": "pediatric_weight_based",
                                     "confidence": 0.85, "provenance": {**prov, "source": "table_cell_pediatric"}})

        return entities

def add_semantic_to_document(doc: Document, engine: str = "unknown") -> None:
    """STEP 2/8/9: semantic layer. Consumes flat text + structured tables (when present).

    Tables from P4.5 Layout give superior cell-level dose/alternative/peds data.
    Backward compatible: flat text path always runs. Table path is additive.
    """
    doc.metadata["semantic_processed"] = False
    processor = SemanticProcessor()
    all_entities: List[Dict[str, Any]] = []
    all_rels: List[Dict[str, Any]] = []
    all_warns: List[str] = []

    for page in doc.pages:
        page_num = getattr(page, "page_num", 0)

        # 1. Always process flat text (mandatory backward compat)
        ents = processor.extract_entities(page.text, page_num, engine)
        page.entities = ents
        rels = processor.extract_relations(page.text, ents)
        warns = processor.check_consistency(ents, rels)
        all_entities.extend(ents)
        all_rels.extend(rels)
        all_warns.extend(warns)

        # 2. P4.5: Structured tables (cell-level, higher fidelity for regimens)
        # Only when available. Does not replace text path.
        if getattr(page, "structured_tables", None):
            table_ents = processor.extract_entities_from_tables(
                page.structured_tables, page_num, engine + "+table"
            )
            # Merge without destroying provenance
            seen_keys = {
                (e['type'], e.get('text', '').lower()[:ENTITY_DEDUP_KEY_LENGTH])
                for e in page.entities
            }
            for te in table_ents:
                k = (te['type'], te.get('text', '').lower()[:ENTITY_DEDUP_KEY_LENGTH])
                if k not in seen_keys:
                    page.entities.append(te)
                    all_entities.append(te)
                    seen_keys.add(k)

    # M-19: the "< 5 entities" threshold was an unexplained magic number.  It is now
    # a named constant with a stated meaning: below this, per-page extraction
    # clearly under-delivered and a whole-document pass is worth its cost.
    MIN_ENTITIES_BEFORE_FULLTEXT_FALLBACK = 5
    if doc.full_text and len(all_entities) < MIN_ENTITIES_BEFORE_FULLTEXT_FALLBACK:
        extra = processor.extract_entities(doc.full_text, -1, engine + "+full")
        seen = {
            (e['type'], e.get('text', '').lower()[:ENTITY_DEDUP_KEY_LENGTH])
            for e in all_entities
        }
        for e in extra:
            k = (e['type'], e.get('text', '').lower()[:ENTITY_DEDUP_KEY_LENGTH])
            if k not in seen:
                all_entities.append(e)
                seen.add(k)

    doc.entities = all_entities
    doc.knowledge_objects = processor.build_knowledge_objects(all_entities)
    doc.metadata["semantic_processed"] = True
    doc.metadata["entity_count"] = len(all_entities)
    doc.metadata["relation_count"] = len(all_rels)
    doc.metadata["semantic_relations"] = all_rels[:20]
    doc.metadata["table_entities_used"] = any("table" in str(e.get("provenance", {}).get("source", "")) for e in all_entities)
    doc.metadata["dictionary_sizes"] = dict(DICTIONARY_SIZES)
    doc.metadata["clinical_normalizer"] = "available" if NORMALIZER is not None else "unavailable"
    if _NORMALIZER_ERROR:
        doc.metadata["clinical_normalizer_error"] = _NORMALIZER_ERROR
    if getattr(processor, "ner_error", None):
        doc.metadata["ner_error"] = processor.ner_error
    doc.metadata["consistency_warnings"] = sorted(set(all_warns))
    doc.metadata["normalization_rate"] = round(
        sum(1 for e in all_entities if "dict_mapped" in str(e.get("normalization_status", ""))) / max(1, len(all_entities)), 3
    ) if all_entities else 0.0
