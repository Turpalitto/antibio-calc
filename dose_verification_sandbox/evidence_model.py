"""Evidence-Integrity Hardening (post-RC-031) — Phase 2/3.

Minimal, reusable contract for any ANTIBIO clinical audit report: every
factual evidence block must declare where it came from and how it was
retrieved, so hand-written prose can never again be rendered as if it were
captured database or PDF output. This is the direct structural fix for how
the RC-031 false finding happened (a HUMAN_NOTE-shaped fabrication rendered
as if it were a DATABASE_QUERY result).

Deliberately small — not a general reporting framework, just enough to make
the failure mode that produced RC-031 mechanically harder to repeat.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

EVIDENCE_ORIGINS = {
    "DATABASE_QUERY", "SOURCE_PDF_EXTRACT", "GENERATED_CALCULATION",
    "HUMAN_NOTE", "PARAPHRASE", "TEST_FIXTURE",
}

# Origins that assert the content is exact, machine-captured output. These
# require source_hash + retrieval_command/query to be non-empty — see
# EvidenceBlock.__post_init__.
_MACHINE_ORIGINS = {"DATABASE_QUERY", "SOURCE_PDF_EXTRACT", "GENERATED_CALCULATION"}


class EvidenceIntegrityError(ValueError):
    """Raised when an evidence block violates the origin contract."""


@dataclass
class EvidenceBlock:
    evidence_origin: str
    source_artifact: str            # e.g. "assembled_regimens.sqlite", "regimen_5574_pdf"
    source_hash: Optional[str]      # SHA-256 of the source file at retrieval time; required for machine origins
    retrieval_command: Optional[str]  # exact SQL query / extraction call; required for machine origins
    retrieved_at: str               # ISO8601 UTC timestamp
    record_identifier: str          # e.g. "assembled_regimens:5574:1"
    is_exact: bool                  # True = verbatim capture, False = paraphrase/summary
    content: str                    # the actual evidence text/value

    def __post_init__(self) -> None:
        if self.evidence_origin not in EVIDENCE_ORIGINS:
            raise EvidenceIntegrityError(f"unknown evidence_origin: {self.evidence_origin}")
        if self.evidence_origin in _MACHINE_ORIGINS:
            if not self.source_hash:
                raise EvidenceIntegrityError(
                    f"{self.evidence_origin} evidence requires a source_hash — "
                    "hand-written text may never claim a machine origin without one"
                )
            if not self.retrieval_command:
                raise EvidenceIntegrityError(
                    f"{self.evidence_origin} evidence requires a retrieval_command/query — "
                    "hand-written text may never claim a machine origin without one"
                )
            if not self.is_exact:
                raise EvidenceIntegrityError(
                    f"{self.evidence_origin} evidence must be is_exact=True — "
                    "a paraphrase cannot claim to be a verbatim machine capture"
                )
        if self.evidence_origin in ("HUMAN_NOTE", "PARAPHRASE") and self.is_exact:
            raise EvidenceIntegrityError(
                f"{self.evidence_origin} evidence cannot be is_exact=True — "
                "commentary/paraphrase is never a verbatim capture by definition"
            )

    def to_dict(self) -> dict:
        return asdict(self)

    def label(self) -> str:
        """Human-facing badge for rendering — makes the origin visually unmissable."""
        if self.evidence_origin == "DATABASE_QUERY":
            return f"[DATABASE QUERY — {self.source_artifact} — verified {self.retrieved_at}]"
        if self.evidence_origin == "SOURCE_PDF_EXTRACT":
            return f"[PDF EXTRACT — {self.source_artifact} — verified {self.retrieved_at}]"
        if self.evidence_origin == "GENERATED_CALCULATION":
            return f"[COMPUTED — {self.source_artifact}]"
        if self.evidence_origin == "TEST_FIXTURE":
            return "[SYNTHETIC TEST FIXTURE — not real data]"
        if self.evidence_origin == "PARAPHRASE":
            return "[PARAPHRASE — not verbatim]"
        return "[COMMENTARY — human note, not verified evidence]"


def compute_packet_hash(packet_without_hash: dict) -> str:
    canonical = json.dumps(packet_without_hash, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_packet(evidence_blocks: list[EvidenceBlock], meta: dict) -> dict:
    body = {"meta": meta, "evidence": [b.to_dict() for b in evidence_blocks]}
    body["packet_hash"] = compute_packet_hash(body)
    return body


def verify_packet(packet: dict) -> bool:
    """Re-derive the packet hash and compare — detects manual editing of a
    previously generated evidence file."""
    claimed = packet.get("packet_hash")
    if claimed is None:
        return False
    body = {k: v for k, v in packet.items() if k != "packet_hash"}
    return compute_packet_hash(body) == claimed


def render_markdown(packet: dict, title: str) -> str:
    """Deterministic Markdown rendering of an evidence packet. Never accepts
    free-text content that bypasses the EvidenceBlock contract — every
    section comes from a validated block's own fields."""
    if not verify_packet(packet):
        raise EvidenceIntegrityError(
            "packet_hash does not match packet content — evidence file may have been "
            "manually edited after generation; refusing to render (fail closed)"
        )

    lines = [f"# {title}", "", "**Auto-generated from a verified evidence packet. Do not hand-edit "
             "this file — regenerate it from the packet instead.**", "",
             f"Packet hash: `{packet['packet_hash']}`", f"Generated at: {packet['meta'].get('generated_at')}", ""]

    for block in packet["evidence"]:
        eb = EvidenceBlock(**{k: v for k, v in block.items()})  # re-validate on render, not just on write
        lines.append(f"## {eb.record_identifier} — {eb.evidence_origin}")
        lines.append("")
        lines.append(eb.label())
        if eb.source_hash:
            lines.append(f"Source: `{eb.source_artifact}` (SHA-256 `{eb.source_hash[:16]}...`)")
        if eb.retrieval_command:
            lines.append(f"Retrieval: `{eb.retrieval_command}`")
        lines.append("")
        lines.append("```")
        lines.append(eb.content)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)
