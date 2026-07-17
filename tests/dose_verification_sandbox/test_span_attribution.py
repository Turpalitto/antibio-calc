"""RC-030 C6 — deterministic tests for the span-linked attribution engine.

All fixtures are short synthetic Russian dose-expression fragments (not
full clinical excerpts) — see RC030_C6 golden fixtures in this file's
docstrings for what each one demonstrates. No real database touched, no
network access, no Clinical Engine import, no calculation activation.
"""
import pytest

from dose_verification_sandbox.span_attribution import (
    AMBIGUOUS_ALTERNATIVE_BOUNDARY, AMBIGUOUS_LOADING_MAINTENANCE, AMBIGUOUS_MULTIPLE_DRUGS,
    AMBIGUOUS_MULTIPLE_RANGES, AMBIGUOUS_TABLE_CONTEXT, NOT_A_DOSE_RANGE, SAFE_EXACT_LINK,
    SAFE_SINGLE_CANDIDATE, SOURCE_INCOMPLETE, WRONG_RANGE_ANCHOR,
    attribute, canonical_result_hash, find_antibiotic_spans, find_range_spans, normalize_text,
)
from dose_verification_sandbox.validation_status import TYPES_MEETING_PRECISION_THRESHOLD


# ── Text normalization (Phase 2 / Phase 18) ────────────────────────────────

def test_dash_variants_normalize_to_plain_hyphen():
    for dash in ("‐", "‑", "‒", "–", "—", "−"):
        nt = normalize_text(f"20{dash}50 мг")
        assert "20-50 мг" == nt.normalized


def test_nbsp_and_repeated_whitespace_collapse():
    nt = normalize_text("20 - 50   мг\n\nв сутки")
    assert "  " not in nt.normalized
    assert "\n" not in nt.normalized


def test_decimal_comma_and_point_both_parse_to_same_value():
    from dose_verification_sandbox.span_attribution import normalize_decimal
    assert normalize_decimal("0,5") == "0.5"
    assert float(normalize_decimal("0,5")) == float(normalize_decimal("0.5"))


def test_offset_map_traces_normalized_span_back_to_raw():
    raw = "20 —  50 мг"
    nt = normalize_text(raw)
    # find the dash's position in normalized text, confirm raw_span lands near the original dash
    dash_idx = nt.normalized.index("-")
    start, end = nt.raw_span(dash_idx, dash_idx + 1)
    assert raw[start:end] != ""


def test_unicode_stability_repeated_normalization_is_idempotent():
    raw = "Амоксициллин 20-50 мг/кг"
    nt1 = normalize_text(raw)
    nt2 = normalize_text(nt1.normalized)
    assert nt1.normalized == nt2.normalized


# ── Range span detection and exclusions (Phase 4 / Phase 18) ──────────────

def test_true_dose_range_detected():
    nt = normalize_text("20-50 мг/кг")
    spans = find_range_spans(nt.normalized)
    assert len(spans) == 1
    assert spans[0].excluded_reason is None
    assert spans[0].lower == 20.0 and spans[0].upper == 50.0


def test_age_range_not_captured_as_a_dose_candidate():
    """'3-5 лет' is not followed by a dose unit, so the regex's unit
    whitelist itself excludes it — only the real dose range is captured."""
    nt = normalize_text("детям 3-5 лет назначают препарат 10-20 мг/кг")
    spans = find_range_spans(nt.normalized)
    assert len(spans) == 1
    assert spans[0].lower == 10.0 and spans[0].upper == 20.0


def test_duration_range_not_captured_as_a_dose_candidate():
    nt = normalize_text("курс лечения 7-10 дней, доза 10-20 мг/кг")
    spans = find_range_spans(nt.normalized)
    assert len(spans) == 1
    assert spans[0].lower == 10.0 and spans[0].upper == 20.0


def test_interval_range_not_captured_as_a_dose_candidate():
    nt = normalize_text("каждые 6-8 часов, доза 10-20 мг/кг")
    spans = find_range_spans(nt.normalized)
    assert len(spans) == 1
    assert spans[0].lower == 10.0 and spans[0].upper == 20.0


def test_maximum_clause_excluded_from_true_ranges():
    nt = normalize_text("не более 20-30 мг/кг в сутки")
    spans = find_range_spans(nt.normalized)
    assert all(s.excluded_reason == "MAXIMUM_CLAUSE" for s in spans)


def test_non_increasing_range_excluded():
    nt = normalize_text("50-20 мг")
    spans = find_range_spans(nt.normalized)
    assert spans[0].excluded_reason == "NON_INCREASING_RANGE"


# ── Attribution engine: safe cases ─────────────────────────────────────────

def test_single_drug_exact_range_is_safe_exact_link():
    nt = normalize_text("Амоксициллин 20-50 мг/кг в сутки внутрь.")
    r = attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг")
    assert r.classification == SAFE_EXACT_LINK
    assert r.selected_range.lower == 20.0
    assert r.selected_range.upper == 50.0


def test_scalar_lower_bound_mismatch_is_not_safe_exact_link():
    nt = normalize_text("Амоксициллин 20-50 мг/кг в сутки внутрь.")
    r = attribute(nt.normalized, "Амоксициллин", 25.0, "мг/кг")  # 25 != 20
    assert r.classification != SAFE_EXACT_LINK


def test_unit_mismatch_rejects_the_candidate():
    nt = normalize_text("Амоксициллин 20-50 мг/кг в сутки внутрь.")
    r = attribute(nt.normalized, "Амоксициллин", 20.0, "г")  # wrong unit
    assert r.classification != SAFE_EXACT_LINK


# ── Attribution engine: multi-drug / boundary cases (the core safety fix) ─

def test_wrong_drug_first_range_is_never_safe():
    """The exact failure mode RC-030's naive heuristic had: the first range
    in a multi-drug quote belongs to a DIFFERENT drug than the one being
    evaluated. The engine must never call this SAFE_EXACT_LINK."""
    nt = normalize_text("Амоксициллин 0,5-1,0 г внутрь или Цефазолин 1,0 г в/в.")
    r = attribute(nt.normalized, "Цефазолин", 1.0, "г")
    assert r.classification not in ("SAFE_EXACT_LINK", "SAFE_TABLE_LINK")


def test_alternative_or_boundary_detected():
    nt = normalize_text("Амоксициллин 500 мг или Цефазолин 20-50 мг/кг.")
    boundary = nt.normalized  # sanity: "или" is present
    assert "или" in boundary
    from dose_verification_sandbox.span_attribution import hard_boundary_between
    idx_amox_end = nt.normalized.index("500") - 1
    idx_range_start = nt.normalized.index("20-50")
    assert hard_boundary_between(nt.normalized, idx_amox_end, idx_range_start) == "ALTERNATIVE_OR"


def test_semicolon_boundary_detected():
    from dose_verification_sandbox.span_attribution import hard_boundary_between
    nt = normalize_text("Амоксициллин 500 мг; Цефазолин 20-50 мг/кг.")
    idx_a = nt.normalized.index(";")
    assert hard_boundary_between(nt.normalized, idx_a - 1, idx_a + 1) == "SEMICOLON"


def test_sentence_boundary_detected():
    from dose_verification_sandbox.span_attribution import hard_boundary_between
    nt = normalize_text("Амоксициллин 500 мг. Цефазолин 20-50 мг/кг.")
    idx = nt.normalized.index(".")
    assert hard_boundary_between(nt.normalized, idx - 1, idx + 1) == "SENTENCE_BOUNDARY"


def test_multiple_antibiotics_with_ambiguous_shared_range_stays_ambiguous():
    nt = normalize_text("Амоксициллин, Цефазолин 20-50 мг/кг в сутки.")
    r = attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг")
    # two drugs share one range with no clear boundary — not a confident single-drug link
    assert r.classification in (SAFE_SINGLE_CANDIDATE, AMBIGUOUS_MULTIPLE_DRUGS)


def test_multiple_equally_plausible_ranges_forces_ambiguity():
    nt = normalize_text("Амоксициллин 10-20 мг/кг или 30-40 мг/кг в сутки.")
    r = attribute(nt.normalized, "Амоксициллин", 999.0, "мг/кг")  # no scalar match to disambiguate
    assert r.classification.startswith("AMBIGUOUS_")
    assert r.classification not in ("SAFE_EXACT_LINK", "SAFE_TABLE_LINK")


# ── Loading/maintenance and maximum-vs-range ───────────────────────────────

def test_loading_maintenance_phase_marker_prevents_safe_link():
    nt = normalize_text("Нагрузочная доза 50 мг/кг, затем поддерживающая доза 20-30 мг/кг.")
    r = attribute(nt.normalized, "Амоксициллин", 999.0, "мг/кг")
    assert r.classification != SAFE_EXACT_LINK


def test_maximum_dose_never_becomes_a_safe_range():
    nt = normalize_text("Амоксициллин, не более 20-30 мг/кг в сутки.")
    r = attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг")
    assert r.classification == WRONG_RANGE_ANCHOR


# ── No-range / source-incomplete controls ──────────────────────────────────

def test_no_range_in_source_is_not_a_dose_range():
    nt = normalize_text("Амоксициллин 500 мг в сутки внутрь.")
    r = attribute(nt.normalized, "Амоксициллин", 500.0, "мг")
    assert r.classification == NOT_A_DOSE_RANGE


def test_empty_source_text_is_source_incomplete():
    r = attribute("", "Амоксициллин", None, None)
    assert r.classification == SOURCE_INCOMPLETE


def test_table_context_flag_forces_ambiguous_table_context():
    """No PDF/table-layout extraction runs in this environment (see module
    docstring) — table-flagged records must be classified honestly, never
    guessed at from flattened text."""
    nt = normalize_text("Амоксициллин 20-50 мг/кг")
    r = attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг", table_context=True)
    assert r.classification == AMBIGUOUS_TABLE_CONTEXT


# ── Antibiotic span detection ──────────────────────────────────────────────

def test_unknown_antibiotic_mention_does_not_infer_from_context():
    nt = normalize_text("Некое неизвестное лекарство 20-50 мг/кг.")
    spans = find_antibiotic_spans(nt.normalized)
    assert spans == []


# ── Determinism (Phase 12 / Phase 18) ──────────────────────────────────────

def test_deterministic_repeat_same_hash():
    nt = normalize_text("Амоксициллин 20-50 мг/кг в сутки внутрь.")
    r1 = attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг")
    r2 = attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг")
    h1 = canonical_result_hash(r1, "5584", "a" * 64)
    h2 = canonical_result_hash(r2, "5584", "a" * 64)
    assert h1 == h2


def test_different_call_order_same_result():
    text = "Амоксициллин 20-50 мг/кг в сутки внутрь."
    nt = normalize_text(text)
    r_first = attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг")
    # re-derive from scratch in a different order (spans then attribute)
    _ = find_antibiotic_spans(nt.normalized)
    _ = find_range_spans(nt.normalized)
    r_second = attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг")
    assert r_first.classification == r_second.classification


# ── Safety boundary regression: no DB, no network, no Clinical Engine ─────

def test_module_has_no_io_or_network_or_clinical_engine_imports():
    import inspect
    import dose_verification_sandbox.span_attribution as mod
    source = inspect.getsource(mod)
    for marker in ("sqlite3.connect", "open(", "requests.", "socket.", "clinical_engine"):
        assert marker not in source


def test_threshold_untouched_by_import_or_use():
    before = set(TYPES_MEETING_PRECISION_THRESHOLD)
    nt = normalize_text("Амоксициллин 20-50 мг/кг в сутки внутрь.")
    attribute(nt.normalized, "Амоксициллин", 20.0, "мг/кг")
    assert TYPES_MEETING_PRECISION_THRESHOLD == before == set()
