"""RC-030 Evidence Validation, Phase 3 — independent high-risk false-positive audit.

This module does NOT use semantics_parser's own classification as ground truth.
It re-derives, from source_quote text alone, whether the region between a
regimen's dose-token anchor and its matched semantic-signal fragment crosses a
boundary that should invalidate the association: an "или" (alternative)
clause, another drug's name (source text consistently wraps drug names in
"**"), a sentence break, or a competing dose number. Any row whose signal
association crosses such a boundary is flagged HIGH_RISK and demoted to
AMBIGUOUS in the validated view, regardless of what semantics_parser said.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .semantics_parser import _find_dose_window, _detect_period_signal, WINDOW_CHARS
from .parser import parse_dose_expression
from .models import UNPARSED

_DRUG_MARKER_RE = re.compile(r"\*\*")
_ALTERNATIVE_RE = re.compile(r"\bили\b", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:мг|г|гр|мл|ед|IU)\b", re.IGNORECASE)
_PEDIATRIC_RE = re.compile(r"дет\w*|педиатр\w*|ребен\w*|ребён\w*", re.IGNORECASE)
_ADULT_RE = re.compile(r"взросл\w*", re.IGNORECASE)

RISK_ALTERNATIVE_BOUNDARY = "CROSSES_ALTERNATIVE_BOUNDARY"
RISK_DRUG_BOUNDARY = "CROSSES_DRUG_NAME_BOUNDARY"
RISK_SENTENCE_BOUNDARY = "CROSSES_SENTENCE_BOUNDARY"
RISK_COMPETING_DOSE = "COMPETING_DOSE_NUMBER_BETWEEN"
RISK_AGE_GROUP_MIX = "MIXED_AGE_GROUP_LANGUAGE"


@dataclass
class RiskAssessment:
    regimen_id: str
    risk_factors: list = field(default_factory=list)
    span_text: str = ""

    @property
    def is_high_risk(self) -> bool:
        return len(self.risk_factors) > 0


def _span_between(window: str, anchor_start: int, anchor_end: int, match_span: tuple[int, int]) -> str:
    """Text strictly between the dose token (anchor_start..anchor_end) and the
    matched signal span — excludes the dose token's own digits/unit."""
    m_start, m_end = match_span
    if anchor_end <= m_start:
        return window[anchor_end:m_start]
    if anchor_start >= m_end:
        return window[m_end:anchor_start]
    return ""  # token and match overlap — no gap to cross


def assess_risk(regimen: dict) -> Optional[RiskAssessment]:
    """Return a RiskAssessment for a regimen already classified with a
    matched_fragment by semantics_parser, or None if there's nothing to
    independently re-check (no window/no fragment)."""
    dose = regimen.get("dose")
    unit = regimen.get("unit") or ""
    frequency = regimen.get("frequency")
    source_quote = regimen.get("source_quote") or ""
    regimen_id = str(regimen.get("regimen_id"))

    expr = parse_dose_expression(dose, unit, frequency)
    if dose is None or expr.parser_status == UNPARSED:
        return None

    window_result = _find_dose_window(source_quote, dose)
    if window_result is None:
        return None
    window, anchor = window_result
    # `anchor` is the START of the matched dose token (e.g. "50" in "50 мг").
    # The gap-analysis below must start AFTER the token, not at its first
    # digit, or the token's own number/unit is counted as a "competing dose".
    token_end_match = re.match(r"\d+(?:[.,]\d+)?", window[anchor:])
    anchor_end = anchor + (len(token_end_match.group(0)) if token_end_match else 0)

    # Re-run the same signal detection to get the match span (not to trust
    # its correctness — to know WHERE in the window the claimed signal is,
    # so this module can independently inspect what lies between it and the
    # dose anchor).
    time_denom, fragment, ambiguity = _detect_period_signal(window, anchor)
    if fragment is None or ambiguity == "AMBIGUOUS_NO_SIGNAL":
        return None  # nothing to risk-check — parser already reports no signal

    idx = window.find(fragment) if fragment else -1
    if idx == -1:
        return RiskAssessment(regimen_id=regimen_id, risk_factors=["FRAGMENT_NOT_LOCATABLE_FOR_AUDIT"])
    match_span = (idx, idx + len(fragment))

    gap_text = _span_between(window, anchor, anchor_end, match_span)

    risks = []
    if _ALTERNATIVE_RE.search(gap_text):
        risks.append(RISK_ALTERNATIVE_BOUNDARY)
    if _DRUG_MARKER_RE.search(gap_text):
        risks.append(RISK_DRUG_BOUNDARY)
    if _SENTENCE_END_RE.search(gap_text):
        risks.append(RISK_SENTENCE_BOUNDARY)
    if len(_NUMBER_RE.findall(gap_text)) > 0:
        risks.append(RISK_COMPETING_DOSE)
    ped_in_gap = _PEDIATRIC_RE.search(gap_text)
    adult_in_gap = _ADULT_RE.search(gap_text)
    row_age = (regimen.get("age_group") or "").lower()
    if (ped_in_gap and "adult" in row_age) or (adult_in_gap and "child" in row_age):
        risks.append(RISK_AGE_GROUP_MIX)

    return RiskAssessment(regimen_id=regimen_id, risk_factors=risks, span_text=gap_text)
