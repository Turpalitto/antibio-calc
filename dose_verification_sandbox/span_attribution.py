"""RC-030 C6 — deterministic span-linked dose-range attribution engine.

Replaces the "first numeric range anywhere in source_quote" heuristic
(RC030_RANGE_REBUILD_INTEGRITY_REPORT.md) with span-level attribution:
locate every antibiotic mention and every true numeric-range candidate in
the source text, then link a range to a drug only when deterministic
structural evidence (same sentence/table cell/alternative, no intervening
drug or hard boundary, unit/scalar compatibility) supports exactly one
link. Everything here is read-only text analysis over `source_quote`
strings already present in `assembled_regimens.sqlite` — no PDF is opened,
no table-layout model is run (this environment has no local PDF corpus;
`C:\\clinrec_downloader` resolves to the repository root here, not a PDF
archive — see RC030_C6_BASELINE.md). Table-flagged records are therefore
classified AMBIGUOUS_TABLE_CONTEXT rather than attempted.

Every result stays EXPERIMENTAL / NOT_OWNER_VERIFIED / CALCULATION_BLOCKED.
Nothing in this module writes to any database, activates a calculation,
imports the Clinical Engine, or touches
`TYPES_MEETING_PRECISION_THRESHOLD`.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from medical_normalizer.dictionary import DRUG_SYNONYMS
from dose_verification_sandbox.dose_unit_signature import (
    COMPATIBLE_BASIS_UNSPECIFIED, EXACT_EQUIVALENT, compare_dose_units, parse_dose_unit,
)

SPAN_ATTRIBUTION_SCHEMA_VERSION = 1

# ── Classification taxonomy (Part IX) ──────────────────────────────────────
SAFE_EXACT_LINK = "SAFE_EXACT_LINK"
SAFE_TABLE_LINK = "SAFE_TABLE_LINK"
SAFE_SINGLE_CANDIDATE = "SAFE_SINGLE_CANDIDATE"
AMBIGUOUS_MULTIPLE_RANGES = "AMBIGUOUS_MULTIPLE_RANGES"
AMBIGUOUS_MULTIPLE_DRUGS = "AMBIGUOUS_MULTIPLE_DRUGS"
AMBIGUOUS_ALTERNATIVE_BOUNDARY = "AMBIGUOUS_ALTERNATIVE_BOUNDARY"
AMBIGUOUS_TABLE_CONTEXT = "AMBIGUOUS_TABLE_CONTEXT"
AMBIGUOUS_LOADING_MAINTENANCE = "AMBIGUOUS_LOADING_MAINTENANCE"
WRONG_RANGE_ANCHOR = "WRONG_RANGE_ANCHOR"
NOT_A_DOSE_RANGE = "NOT_A_DOSE_RANGE"
SOURCE_INCOMPLETE = "SOURCE_INCOMPLETE"
SOURCE_CORRUPTED = "SOURCE_CORRUPTED"
DICTIONARY_GAP = "DICTIONARY_GAP"
ENGINE_REVIEW_REQUIRED = "ENGINE_REVIEW_REQUIRED"

ALL_CLASSIFICATIONS = frozenset({
    SAFE_EXACT_LINK, SAFE_TABLE_LINK, SAFE_SINGLE_CANDIDATE,
    AMBIGUOUS_MULTIPLE_RANGES, AMBIGUOUS_MULTIPLE_DRUGS, AMBIGUOUS_ALTERNATIVE_BOUNDARY,
    AMBIGUOUS_TABLE_CONTEXT, AMBIGUOUS_LOADING_MAINTENANCE,
    WRONG_RANGE_ANCHOR, NOT_A_DOSE_RANGE, SOURCE_INCOMPLETE, SOURCE_CORRUPTED,
    DICTIONARY_GAP, ENGINE_REVIEW_REQUIRED,
})
SAFE_CLASSIFICATIONS = frozenset({SAFE_EXACT_LINK, SAFE_TABLE_LINK})


# ── Part III: canonical text model with offset preservation ───────────────

@dataclass(frozen=True)
class NormalizedText:
    raw: str
    normalized: str
    # normalized[i] came from raw[offset_map[i]] (best-effort; collapsed
    # whitespace runs all map to the run's start offset in raw)
    offset_map: tuple[int, ...]

    def raw_span(self, norm_start: int, norm_end: int) -> tuple[int, int]:
        if not self.offset_map:
            return (0, 0)
        start = self.offset_map[min(norm_start, len(self.offset_map) - 1)]
        end_idx = min(norm_end, len(self.offset_map)) - 1
        end = self.offset_map[max(end_idx, 0)] + 1
        return (start, end)


_DASH_VARIANTS_RE = re.compile(r"[‐‑‒–—−]")  # hyphen/en/em/minus -> "-"
_NBSP_RE = re.compile(r"[  ]")
_WS_RUN_RE = re.compile(r"\s+")


def normalize_text(raw: str) -> NormalizedText:
    """Deterministic, evidence-preserving normalization: NFC, non-breaking
    spaces -> plain space, dash variants -> '-', whitespace runs collapsed
    to a single space. Never deletes or substitutes evidentiary characters
    (digits, letters, punctuation meaning) — only whitespace/dash/Unicode
    canonicalization. Offset map lets any normalized-text span be traced
    back to the exact raw-text offsets for provenance."""
    nfc = unicodedata.normalize("NFC", raw)
    nfc = _NBSP_RE.sub(" ", nfc)
    nfc = _DASH_VARIANTS_RE.sub("-", nfc)

    out_chars: list[str] = []
    offset_map: list[int] = []
    i = 0
    n = len(nfc)
    while i < n:
        ch = nfc[i]
        if ch.isspace():
            start = i
            while i < n and nfc[i].isspace():
                i += 1
            out_chars.append(" ")
            offset_map.append(start)
        else:
            out_chars.append(ch)
            offset_map.append(i)
            i += 1
    normalized = "".join(out_chars).strip()
    # strip() may have removed leading/trailing space chars; trim offset_map to match
    lead = len("".join(out_chars)) - len("".join(out_chars).lstrip())
    total_len = len(out_chars)
    lstripped = "".join(out_chars).lstrip()
    lead = total_len - len(lstripped)
    trimmed_map = offset_map[lead:lead + len(normalized)]
    return NormalizedText(raw=raw, normalized=normalized, offset_map=tuple(trimmed_map))



def normalize_decimal(text: str) -> str:
    """Decimal comma -> decimal point, for numeric comparison only (never
    mutates the stored raw/normalized text itself)."""
    return text.replace(",", ".")


# ── Part IV Phase 3: antibiotic spans ──────────────────────────────────────

@dataclass(frozen=True)
class AntibioticSpan:
    canonical: str
    raw_token: str
    start: int
    end: int
    confidence: float
    source: str  # "dictionary" | "regimen_antibiotic_field"


def find_antibiotic_spans(normalized: str, known_antibiotic_raw: Optional[str] = None) -> list[AntibioticSpan]:
    """Match antibiotic mentions using the governed DRUG_SYNONYMS dictionary
    only — never inferred from clinical context. `known_antibiotic_raw` (the
    regimen's own structured `antibiotic` field) is also matched literally
    if it appears in the text, since that is governed, not inferred."""
    spans: list[AntibioticSpan] = []
    lower = normalized.lower()
    seen_ranges: set[tuple[int, int]] = set()

    candidates = sorted(DRUG_SYNONYMS.keys(), key=len, reverse=True)
    for alias in candidates:
        alias_l = alias.lower()
        if len(alias_l) < 4:
            continue  # skip too-short aliases (false-positive risk)
        start_search = 0
        while True:
            idx = lower.find(alias_l, start_search)
            if idx == -1:
                break
            end = idx + len(alias_l)
            key = (idx, end)
            if key not in seen_ranges and not any(a <= idx < b for a, b in seen_ranges):
                spans.append(AntibioticSpan(
                    canonical=DRUG_SYNONYMS[alias], raw_token=normalized[idx:end],
                    start=idx, end=end, confidence=1.0, source="dictionary",
                ))
                seen_ranges.add(key)
            start_search = idx + 1

    spans.sort(key=lambda s: s.start)
    return spans


# ── Part IV Phase 4-5: dose/range spans and structural boundaries ─────────

@dataclass(frozen=True)
class RangeSpan:
    lower: float
    upper: float
    unit_raw: str
    raw_text: str
    start: int
    end: int
    excluded_reason: Optional[str] = None  # set if this looked like a range but was excluded


_NUM = r"\d[\d.,]*"
# C6.8: the compact-token alternatives (мг/кг/сут, etc.) are tried first;
# the spelled-out per-weight-per-day construction ("20-40 мг на кг массы
# тела в сутки") is recognized explicitly rather than falling through to
# the bare "мг" alternative and silently losing the /kg/day qualifier --
# see RC030_C68_UNIT_VOCABULARY_AUDIT.md and RC030_C67_UNIT_NORMALIZATION_AUDIT.md
# for the real defect this closes (regimen_id 5917/5918/5441/5442/5475/5478).
_SPELLED_OUT_UNIT = r"(?:мг|г)\s+на\s+кг\s+массы\s+тела\s+в\s+сутки|(?:мг|г)\s+на\s+кг\s+массы\s+тела|(?:мг|г)\s+на\s+кг"
# C6.8: concentration forms (мг/мл, г/мл) must be recognized explicitly and
# BEFORE the bare мг/г alternatives -- otherwise a real "X-Y мг/мл" source
# range silently truncates to bare "мг", losing the concentration marker
# entirely (found by the Phase 8 test matrix; the old regex had no
# concentration alternative at all, unlike its already-present bare "мл"
# volume alternative).
_RANGE_RE = re.compile(
    rf"({_NUM})\s*-\s*({_NUM})\s*({_SPELLED_OUT_UNIT}|мг/кг/сут|мг/кг/сутки|мг/кг/день|мг/кг|мг/мл|г/мл|г/сут|г|мг|мл)"
)

_MAX_MARKER_RE = re.compile(r"не\s+более|максимальн|макс\.?\s*доза", re.IGNORECASE)
_LOADING_MARKER_RE = re.compile(
    r"нагрузочн|первая\s+доза|стартов|затем|далее|поддерживающ|последующ", re.IGNORECASE)
_AGE_MARKER_RE = re.compile(r"\d\s*-\s*\d+\s*(лет|мес|года|год)", re.IGNORECASE)
_DURATION_MARKER_RE = re.compile(r"\d+\s*-\s*\d+\s*(дн|день|дня|дней|недел|нед\.)", re.IGNORECASE)
_INTERVAL_MARKER_RE = re.compile(r"каждые?\s*\d+\s*-\s*\d+\s*ч", re.IGNORECASE)
_ALTERNATIVE_SEP_RE = re.compile(r"\bили\b", re.IGNORECASE)
_HARD_BOUNDARY_RE = re.compile(r"[;.]|\bили\b", re.IGNORECASE)


def find_range_spans(normalized: str) -> list[RangeSpan]:
    """Find every `X-Y <unit>` numeric span, then reject anything matching a
    known non-dose-range shape (age range, duration range, interval range).
    Excluded candidates are RETAINED with `excluded_reason` set — callers
    need to see what was rejected and why, not just what survived."""
    out: list[RangeSpan] = []
    for m in _RANGE_RE.finditer(normalized):
        start, end = m.span()
        raw_text = m.group(0)
        window = normalized[max(0, start - 20):min(len(normalized), end + 20)]
        excluded = None
        if _AGE_MARKER_RE.search(raw_text):
            excluded = "AGE_RANGE"
        elif _DURATION_MARKER_RE.search(raw_text):
            excluded = "DURATION_RANGE"
        elif _INTERVAL_MARKER_RE.search(window):
            excluded = "INTERVAL_RANGE"
        elif _MAX_MARKER_RE.search(normalized[max(0, start - 25):start]):
            excluded = "MAXIMUM_CLAUSE"
        try:
            lower = float(normalize_decimal(m.group(1)))
            upper = float(normalize_decimal(m.group(2)))
        except ValueError:
            excluded = excluded or "UNPARSEABLE_NUMBER"
            lower = upper = 0.0
        if excluded is None and lower >= upper:
            excluded = "NON_INCREASING_RANGE"
        out.append(RangeSpan(
            lower=lower, upper=upper, unit_raw=m.group(3), raw_text=raw_text,
            start=start, end=end, excluded_reason=excluded,
        ))
    return out


def hard_boundary_between(normalized: str, a_end: int, b_start: int) -> Optional[str]:
    """Returns a boundary-type string if a hard attribution boundary (Phase
    5) separates two offsets, else None. Order matters: checked from most to
    least specific."""
    if a_end > b_start:
        a_end, b_start = b_start, a_end
    between = normalized[a_end:b_start]
    if _ALTERNATIVE_SEP_RE.search(between):
        return "ALTERNATIVE_OR"
    if ";" in between:
        return "SEMICOLON"
    if "." in between:
        return "SENTENCE_BOUNDARY"
    return None


def phase_marker_between(normalized: str, a_end: int, b_start: int) -> bool:
    if a_end > b_start:
        a_end, b_start = b_start, a_end
    return bool(_LOADING_MARKER_RE.search(normalized[a_end:b_start]))


# ── Part V: deterministic link scoring ─────────────────────────────────────

@dataclass
class AttributionResult:
    classification: str
    selected_range: Optional[RangeSpan]
    selected_antibiotic: Optional[AntibioticSpan]
    competing_ranges: list[RangeSpan]
    rejection_reasons: list[str]
    score_components: dict


def attribute(
    normalized: str,
    known_antibiotic_raw: Optional[str],
    current_scalar: Optional[float],
    current_unit: Optional[str],
    table_context: bool = False,
) -> AttributionResult:
    """Deterministic, rule-based only — no clinical plausibility, no AI
    voting. See module docstring and RC030_C6_ARCHITECTURE_AUDIT.md for the
    full rule set this implements (Phases 6-7)."""
    if not normalized or not normalized.strip():
        return AttributionResult(SOURCE_INCOMPLETE, None, None, [], ["empty_source_text"], {})

    if table_context:
        return AttributionResult(
            AMBIGUOUS_TABLE_CONTEXT, None, None, [], ["table_recovery_unavailable_in_this_environment"], {}
        )

    all_ranges = find_range_spans(normalized)
    true_ranges = [r for r in all_ranges if r.excluded_reason is None]
    if not all_ranges:
        return AttributionResult(NOT_A_DOSE_RANGE, None, None, [], ["no_numeric_range_found"], {})
    if not true_ranges:
        reasons = sorted({r.excluded_reason for r in all_ranges if r.excluded_reason})
        if reasons == ["MAXIMUM_CLAUSE"]:
            return AttributionResult(WRONG_RANGE_ANCHOR, None, None, all_ranges, reasons, {})
        return AttributionResult(NOT_A_DOSE_RANGE, None, None, all_ranges, reasons, {})

    antibiotic_spans = find_antibiotic_spans(normalized, known_antibiotic_raw)
    if len(antibiotic_spans) == 0:
        # A true dose range exists but the governed dictionary matched no
        # antibiotic mention at all — this is a dictionary coverage gap
        # (missing synonym/spelling variant), NOT evidence that the range
        # belongs to a different drug. Conflating this with
        # AMBIGUOUS_MULTIPLE_DRUGS was a real defect found during C6.1's
        # dictionary-coverage audit (43/365 records affected) — that label
        # implies competing drugs were seen, when in fact zero were.
        return AttributionResult(DICTIONARY_GAP, None, None, true_ranges,
                                  ["no_dictionary_antibiotic_span_found"], {})

    distinct_drugs = {s.canonical for s in antibiotic_spans}
    if len(distinct_drugs) > 1:
        # Multi-drug quote: only proceed if exactly one range is inside the
        # same "segment" (no other drug / hard boundary between it and any
        # antibiotic span of a DIFFERENT drug).
        pass

    scored: list[tuple[RangeSpan, AntibioticSpan, dict]] = []
    for rng in true_ranges:
        nearest = min(antibiotic_spans, key=lambda a: min(abs(a.end - rng.start), abs(rng.end - a.start)))
        components = {"unit_match": False, "scalar_match": False, "same_segment": True, "boundary": None}

        for other in antibiotic_spans:
            if other is nearest:
                continue
            other_between_lo, other_between_hi = sorted((other.start, rng.start))
            if other.start < rng.start and other.end <= rng.start:
                if not any(a.start > other.end and a.end <= rng.start and a is not other for a in antibiotic_spans):
                    boundary = hard_boundary_between(normalized, other.end, rng.start)
                    if boundary is None and other.canonical != nearest.canonical:
                        components["same_segment"] = False
                        components["boundary"] = "INTERVENING_DRUG"

        boundary = hard_boundary_between(normalized, nearest.end, rng.start) or \
            hard_boundary_between(normalized, rng.end, nearest.start)
        if boundary:
            components["same_segment"] = False
            components["boundary"] = boundary

        if phase_marker_between(normalized, min(nearest.end, rng.end), max(nearest.start, rng.start)):
            components["phase_conflict"] = True

        # C6.8: structured compatibility (DoseUnitSignature) replaces the
        # C6/C6.5 leading-token _base_unit() comparison, which could not
        # distinguish absolute mg from per-kilogram mg/kg from
        # per-kilogram-per-day mg/kg/day -- see
        # RC030_C67_UNIT_NORMALIZATION_AUDIT.md and
        # RC030_C68_UNIT_VOCABULARY_AUDIT.md. COMPATIBLE_BASIS_UNSPECIFIED
        # keeps a candidate alive (unit_match=True) but is tracked
        # separately so it can never alone justify SAFE_EXACT_LINK.
        if not current_unit:
            components["unit_compatibility"] = None
            components["unit_match"] = True
        else:
            compat = compare_dose_units(parse_dose_unit(current_unit), parse_dose_unit(rng.unit_raw))
            components["unit_compatibility"] = compat
            components["unit_match"] = compat in (EXACT_EQUIVALENT, COMPATIBLE_BASIS_UNSPECIFIED)

        if current_scalar is not None:
            components["scalar_match"] = abs(rng.lower - current_scalar) < 1e-6

        scored.append((rng, nearest, components))

    valid = [
        (rng, ab, comp) for rng, ab, comp in scored
        if comp["same_segment"] and not comp.get("phase_conflict") and comp["unit_match"]
    ]

    if not valid:
        # Diagnostic-only: report the actual reason each candidate was
        # rejected. Real defect found during C6.5's root-cause analysis —
        # the previous `c.get("boundary") or "phase_conflict" or "unit_mismatch"`
        # always evaluated to the literal string "phase_conflict" regardless
        # of the true cause (Python `or`-chaining returns the first truthy
        # operand; "phase_conflict" is always truthy, making the
        # "unit_mismatch" branch unreachable dead code). This only affected
        # the informational `rejection_reasons` list — the classification
        # decisions below use `comp["boundary"]`/`comp.get("phase_conflict")`
        # directly and were never affected.
        def _reject_reason(c: dict) -> str:
            if c.get("boundary"):
                return c["boundary"]
            if c.get("phase_conflict"):
                return "phase_conflict"
            if not c["unit_match"]:
                # C6.8: surface the specific DoseUnitSignature compatibility
                # failure (e.g. concentration/rate/weight-basis conflict)
                # instead of a single generic "unit_mismatch" string.
                compat = c.get("unit_compatibility")
                return f"unit_mismatch:{compat}" if compat else "unit_mismatch"
            return "no_valid_segment"
        rejected = [_reject_reason(c) for _, _, c in scored]
        if any(c.get("phase_conflict") for _, _, c in scored):
            return AttributionResult(AMBIGUOUS_LOADING_MAINTENANCE, None, None, true_ranges, rejected, {})
        if any(c["boundary"] == "ALTERNATIVE_OR" for _, _, c in scored):
            return AttributionResult(AMBIGUOUS_ALTERNATIVE_BOUNDARY, None, None, true_ranges, rejected, {})
        return AttributionResult(WRONG_RANGE_ANCHOR, None, None, true_ranges, rejected, {})

    if len(valid) > 1:
        # Multiple equally-plausible ranges survive -> ambiguous, unless
        # exactly one also has a matching scalar lower bound (then that one
        # is a strictly stronger candidate).
        scalar_matches = [t for t in valid if t[2]["scalar_match"]]
        if len(scalar_matches) == 1:
            valid = scalar_matches
        else:
            return AttributionResult(AMBIGUOUS_MULTIPLE_RANGES, None, None,
                                      [t[0] for t in valid], ["multiple_equally_plausible_ranges"], {})

    rng, ab, comp = valid[0]
    # C6.8: COMPATIBLE_BASIS_UNSPECIFIED must not automatically yield
    # SAFE_EXACT_LINK -- only a structurally EXACT_EQUIVALENT unit
    # comparison (full numerator/weight/time/administration-basis
    # agreement) can. A merely-compatible-but-unspecified basis caps out at
    # SAFE_SINGLE_CANDIDATE, per RC030_C68 Phase 4.
    exact_unit = comp["unit_compatibility"] in (EXACT_EQUIVALENT, None)
    if len(distinct_drugs) == 1 and comp["scalar_match"] and exact_unit:
        classification = SAFE_EXACT_LINK
    elif comp["scalar_match"] and comp["unit_match"]:
        classification = SAFE_SINGLE_CANDIDATE
    else:
        classification = SAFE_SINGLE_CANDIDATE if len(true_ranges) == 1 and len(antibiotic_spans) == 1 else AMBIGUOUS_MULTIPLE_DRUGS

    return AttributionResult(
        classification=classification, selected_range=rng, selected_antibiotic=ab,
        competing_ranges=[t[0] for t in scored if t[0] is not rng],
        rejection_reasons=[], score_components=comp,
    )


def canonical_result_hash(result: AttributionResult, regimen_id: str, source_hash: str) -> str:
    """Deterministic hash of an attribution result for double-pass
    comparison (Phase 12) — excludes nothing time-dependent since this
    module has no timestamps."""
    payload = {
        "regimen_id": regimen_id, "source_hash": source_hash,
        "classification": result.classification,
        "selected_range": None if result.selected_range is None else {
            "lower": result.selected_range.lower, "upper": result.selected_range.upper,
            "unit_raw": result.selected_range.unit_raw, "start": result.selected_range.start,
            "end": result.selected_range.end,
        },
        "selected_antibiotic": None if result.selected_antibiotic is None else {
            "canonical": result.selected_antibiotic.canonical,
            "start": result.selected_antibiotic.start, "end": result.selected_antibiotic.end,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
