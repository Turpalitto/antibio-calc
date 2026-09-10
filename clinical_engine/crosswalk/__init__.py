"""Calculator ⇄ clinical-guideline corpus crosswalk (navigation layer).

Why this package exists
-----------------------
Two identifier namespaces coexist in this repository and they do **not**
overlap:

* the HTML calculator (``db/antibio_db.json``) keys every nozology by the
  Минздрав rubricator id — ``cr_id`` such as ``"858_1"``;
* the extracted guideline corpus (``clinical_engine/resources/
  diagnosis_index.json``) keys every guideline by an **internal**
  ``metadata.sqlite`` row id — ``guideline_id`` such as ``"1269"``.

Verified 2026-09-10: of 82 distinct rubricator numbers used by the
calculator, exactly **one** (``912``) also appears as a corpus
``guideline_id`` — and that single hit is a false positive
(``КР912_1`` «Неонатальный сепсис» vs corpus 912 «Системный склероз»).
The two namespaces must therefore never be joined by id.

The only sound join keys are **ICD-10** and, secondarily, the exact
normalized guideline title / diagnosis name. This package computes that
join deterministically and emits a reviewable artifact.

Safety contract (permanent)
---------------------------
The crosswalk is **navigation only**. It never approves a regimen, never
unblocks ``calculation_blocked``, never feeds the recommendation pipeline
and never invents a source URL. Every link records the codes/titles that
produced it so a physician can re-derive the decision.
"""

from __future__ import annotations

from .builder import (
    BUILDER_VERSION,
    DEFAULT_CALCULATOR_DB,
    DEFAULT_DIAGNOSIS_INDEX,
    DEFAULT_OUTPUT,
    CrosswalkBuildError,
    METHOD_CONFIDENCE,
    METHOD_ICD10_BLOCK,
    METHOD_ICD10_EXACT,
    METHOD_PRIORITY,
    METHOD_TITLE_EXACT,
    PURPOSE,
    SCHEMA_VERSION,
    build_crosswalk,
    build_crosswalk_from_paths,
    canonical_json,
    compact_links,
    content_sha256,
    crosswalk_summary,
    icd_block,
    normalize_icd10_values,
    normalize_text,
    write_crosswalk,
)
from .reader import CalculatorCrosswalk

__all__ = [
    "BUILDER_VERSION",
    "CalculatorCrosswalk",
    "CrosswalkBuildError",
    "DEFAULT_CALCULATOR_DB",
    "DEFAULT_DIAGNOSIS_INDEX",
    "DEFAULT_OUTPUT",
    "METHOD_CONFIDENCE",
    "METHOD_ICD10_BLOCK",
    "METHOD_ICD10_EXACT",
    "METHOD_PRIORITY",
    "METHOD_TITLE_EXACT",
    "PURPOSE",
    "SCHEMA_VERSION",
    "build_crosswalk",
    "build_crosswalk_from_paths",
    "canonical_json",
    "compact_links",
    "content_sha256",
    "crosswalk_summary",
    "icd_block",
    "normalize_icd10_values",
    "normalize_text",
    "write_crosswalk",
]
