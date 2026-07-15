"""Unit tests for prefilter.classify_item with rule priority semantics."""

import pytest
from prefilter import classify_item, _default_decision

# Minimal rules subset for testing
BASE_RULES = {
    "version": "1.0",
    "defaults": {
        "has_antibiotics_True_abx_level_AB": "need_llm",
        "has_antibiotics_True_abx_level_CD": "need_llm",
        "has_antibiotics_False_abx_score_gte_10": "review",
        "has_antibiotics_False_abx_score_lt_10": "no_antibiotics",
        "has_antibiotics_False_abx_score_null": "no_antibiotics",
    },
    "rules": {
        "force_include": {
            "priority": 100,
            "match_any": {"name_keywords": ["инфекци", "пневмони", "менингит"]},
        },
        "force_review": {
            "priority": 80,
            "match_any": {"name_keywords": ["онкологи", "травм", "опухол"]},
        },
        "force_exclude": {
            "priority": 90,
            "require": {"has_antibiotics": False, "abx_score_lt": 5},
            "match_any": {"name_keywords": ["вакцин"]},
        },
    },
}


# ── Scenario 1: A+B default=need_llm, force_include matches, force_review also matches ──
def test_force_include_wins_over_force_review():
    """force_include (p100) takes priority over force_review (p80) when both match."""
    item = {
        "Id": 1,
        "Name": "Инфекционные осложнения при онкологических заболеваниях",
        "Mkbs": [],
        "has_antibiotics": True,
        "abx_level": "A",
        "abx_score": 80,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "need_llm", (
        f"force_include should win, got {result['final_decision']}"
    )
    assert result["matched_rule"] == "force_include", (
        f"matched_rule should be force_include, got {result['matched_rule']}"
    )


# ── Scenario 2: force_include matches, default is already need_llm (A+B) ──
def test_force_include_confirms_default():
    """force_include should lock so force_review cannot override even if default unchanged."""
    item = {
        "Id": 2,
        "Name": "Менингит бактериальный",
        "Mkbs": [{"MkbCode": "G00"}],
        "has_antibiotics": True,
        "abx_level": "A",
        "abx_score": 90,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "need_llm"
    assert result["matched_rule"] == "force_include"
    assert result["override"] is False  # confirmed default, unchanged


# ── Scenario 3: force_include overrides default (has_antibiotics=False → need_llm) ──
def test_force_include_overrides_default_no_abx():
    """force_include promotes no_antibiotics default to need_llm."""
    item = {
        "Id": 3,
        "Name": "Инфекция мочевыводящих путей",
        "Mkbs": [{"MkbCode": "N39"}],
        "has_antibiotics": False,
        "abx_level": "D",
        "abx_score": 0,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "need_llm"
    assert result["matched_rule"] == "force_include"
    assert result["override"] is True


# ── Scenario 4: force_review alone (no force_include match) ──
def test_force_review_alone():
    """force_review pushes A+B to review when no infection keywords."""
    item = {
        "Id": 4,
        "Name": "Онкологическое заболевание",
        "Mkbs": [{"MkbCode": "C50"}],
        "has_antibiotics": True,
        "abx_level": "B",
        "abx_score": 40,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "review"
    assert result["matched_rule"] == "force_review"
    assert result["override"] is True


# ── Scenario 5: force_exclude wins over force_review (higher priority) ──
def test_force_exclude_wins_over_force_review():
    """force_exclude (p90) beats force_review (p80)."""
    item = {
        "Id": 5,
        "Name": "Вакцинопрофилактика травм",
        "Mkbs": [],
        "has_antibiotics": False,
        "abx_level": "D",
        "abx_score": 0,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "no_antibiotics"
    assert result["matched_rule"] == "force_exclude"


# ── Scenario 6: no_rules_match → default applies ──
def test_default_no_abx():
    """No matching rules → default decision applies."""
    item = {
        "Id": 6,
        "Name": "Глаукома",
        "Mkbs": [{"MkbCode": "H40"}],
        "has_antibiotics": False,
        "abx_level": "D",
        "abx_score": 0,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "no_antibiotics"
    assert result["matched_rule"] is None
    assert result["override"] is False


# ── Scenario 7: A+B with no matching rules → default need_llm ──
def test_default_ab_active():
    item = {
        "Id": 7,
        "Name": "Острый пиелонефрит",
        "Mkbs": [{"MkbCode": "N10"}],
        "has_antibiotics": True,
        "abx_level": "A",
        "abx_score": 75,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "need_llm"
    assert result["override"] is False


# ── Scenario 8: has_antibiotics=False but high score → default review ──
def test_default_review():
    item = {
        "Id": 8,
        "Name": "Трофическая язва",
        "Mkbs": [],
        "has_antibiotics": False,
        "abx_level": "D",
        "abx_score": 15,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "review"
    assert result["matched_rule"] is None
    assert result["override"] is False


# ── Scenario 9: no mkbs in item ──
def test_no_mkbs():
    item = {
        "Id": 9,
        "Name": "Пневмония",
        "Mkbs": [],
        "has_antibiotics": True,
        "abx_level": "A",
        "abx_score": 85,
    }
    result = classify_item(item, BASE_RULES)
    assert result["final_decision"] == "need_llm"
    assert result["matched_rule"] == "force_include"
