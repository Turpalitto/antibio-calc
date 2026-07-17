"""RC-030 Part III — Source-Backed Dose Semantics Validation Program.

Defines the atomic validation record (`DoseSemanticEvidenceUnit`) and the
controlled taxonomies for human fidelity review. This module is additive and
experimental: nothing here changes `calculation_eligibility` computed by
`validation_status.py`, and no field in this file feeds back into the
calculator. Parser output alone remains UNVALIDATED regardless of anything
recorded through this schema.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Optional

# Identity contract (RC-030 C4 Phase 2 decision, documented in full in
# RC030_C4_ARCHITECTURE_AUDIT.md): a validation unit identifies one
# reviewable parser CLAIM about one source packet. `parser_version` is
# deliberately NOT part of the identity hash — a re-run of a newer parser
# over the same unchanged source evidence is describing the same reviewable
# claim (same dose_token/marker/source_quote/offsets), so a stale review
# should still apply to it; parser_version travels alongside as informational
# provenance instead (also recorded on the owner event, where staleness is
# actually enforced against the *current* record). What DOES change identity:
# regimen_id, regimen_version, and every source-evidence field (source_pdf,
# source_page, dose_token/offsets, marker/offsets, source_quote,
# sentence/alternative boundaries, table position) — i.e. anything that
# describes *what claim is being reviewed*, not *which tool produced it*.
VALIDATION_UNIT_SCHEMA_VERSION = 1

_IDENTITY_FIELDS = (
    "regimen_id", "regimen_version", "antibiotic", "diagnosis",
    "dose_token", "dose_token_start", "dose_token_end",
    "source_semantic_marker", "marker_start", "marker_end",
    "source_quote", "sentence_boundary", "alternative_boundary",
    "table_row", "table_column",
    "source_pdf", "source_page",
    "parser_semantic_type",
)

HUMAN_FIDELITY_VERDICTS = {
    "CORRECT_EXPLICIT_PER_DAY", "CORRECT_EXPLICIT_PER_DOSE", "CORRECT_FIXED_DAILY",
    "CORRECT_FIXED_SINGLE", "CORRECT_RANGE_DAILY", "CORRECT_RANGE_SINGLE",
    "WRONG_DOSE_ANCHOR", "WRONG_SEMANTIC_MARKER", "WRONG_FREQUENCY_LINK",
    "WRONG_ALTERNATIVE", "WRONG_AGE_GROUP", "WRONG_TABLE_ROW",
    "SOURCE_INCOMPLETE", "SOURCE_CORRUPTED", "TABLE_CONTEXT_REQUIRED",
    "REMAINS_AMBIGUOUS", "NOT_A_DOSABLE_REGIMEN",
}

EVIDENCE_LEVELS_V2 = {
    "QUOTE_EXPLICIT", "SENTENCE_EXPLICIT", "TABLE_CELL_EXPLICIT",
    "TABLE_HEADER_INHERITANCE", "FOOTNOTE_EXPLICIT", "STRUCTURE_RECOVERED",
    "INSUFFICIENT",
}

VALIDATION_STATUSES_V2 = {
    "UNVALIDATED", "HUMAN_SOURCE_VALIDATED", "STRUCTURE_VALIDATED",
    "REJECTED", "AMBIGUOUS", "SOURCE_RECOVERY_REQUIRED",
}

EVIDENCE_ORIGINS_V2 = {
    "EXACT_DATABASE_RESULT", "EXACT_SOURCE_QUOTE", "PDF_EXTRACTION",
    "PARSER_OUTPUT", "HUMAN_COMMENTARY", "PARAPHRASE",
}


@dataclass
class DoseSemanticEvidenceUnit:
    unit_id: str
    regimen_id: str
    regimen_version: int
    antibiotic: str
    diagnosis: str

    dose_token: str
    dose_token_start: int
    dose_token_end: int

    source_semantic_marker: Optional[str]
    marker_start: Optional[int]
    marker_end: Optional[int]

    source_quote: str
    sentence_boundary: Optional[tuple[int, int]]
    alternative_boundary: Optional[tuple[int, int]]
    table_row: Optional[int]
    table_column: Optional[str]

    frequency: Optional[float]
    route: Optional[str]

    source_pdf: str
    source_page: str
    provenance: str

    parser_semantic_type: str
    parser_rule_id: str
    parser_confidence: Optional[float]

    human_fidelity_verdict: Optional[str] = None
    evidence_level: str = "INSUFFICIENT"
    validation_status: str = "UNVALIDATED"
    calculation_eligibility: str = "BLOCKED"

    validated_by: Optional[str] = None
    validated_at: Optional[str] = None

    validation_unit_schema_version: int = VALIDATION_UNIT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.human_fidelity_verdict is not None and self.human_fidelity_verdict not in HUMAN_FIDELITY_VERDICTS:
            raise ValueError(f"invalid human_fidelity_verdict: {self.human_fidelity_verdict}")
        if self.evidence_level not in EVIDENCE_LEVELS_V2:
            raise ValueError(f"invalid evidence_level: {self.evidence_level}")
        if self.validation_status not in VALIDATION_STATUSES_V2:
            raise ValueError(f"invalid validation_status: {self.validation_status}")
        # Fail-closed: this schema never grants calculation eligibility on its
        # own. A human_fidelity_verdict alone is not sufficient; that
        # decision is made exclusively by validation_status.py's precision
        # gate (TYPES_MEETING_PRECISION_THRESHOLD), never by this module.
        if self.calculation_eligibility != "BLOCKED":
            raise ValueError(
                "DoseSemanticEvidenceUnit.calculation_eligibility must remain BLOCKED; "
                "eligibility is computed exclusively by validation_status.validate()"
            )

    def canonical_identity_payload(self) -> dict:
        """The subset of fields that define *what claim is being reviewed*
        (see `_IDENTITY_FIELDS` module docstring for the identity contract).
        Deliberately excludes `validated_at`/`validated_by` (timestamps and
        reviewer identity are not part of the claim's identity — the same
        claim can be reviewed, and re-reviewed, without becoming a different
        claim) and `parser_rule_id`/`parser_confidence` (provenance, not
        identity). Field order is fixed by `_IDENTITY_FIELDS`, not dict
        insertion order, so the payload is stable regardless of how the
        dataclass was constructed."""
        full = asdict(self)
        return {k: full[k] for k in _IDENTITY_FIELDS}

    def compute_identity_hash(self) -> str:
        """Deterministic sha256 over the canonical identity payload.

        - Field-order independent: `_IDENTITY_FIELDS` fixes serialization
          order regardless of construction order.
        - No timestamps, no `validated_by`, no filesystem paths (source_pdf
          is a document *name*, not an absolute local path — validated
          separately, see tests).
        - `json.dumps(..., sort_keys=True, ensure_ascii=False)` gives a
          stable, encoding-independent (UTF-8) byte representation; tuples
          (sentence_boundary/alternative_boundary) serialize as JSON arrays
          so `(1, 2)` and `[1, 2]` hash identically if ever mixed.
        - Same inputs -> same hash (deterministic construction).
        - Any identity-field change -> different hash (materially different
          evidence produces a different identity)."""
        payload = self.canonical_identity_payload()
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=list)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
