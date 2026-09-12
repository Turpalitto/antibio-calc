"""PHYSICIAN_PILOT_V1 — named, explicit pilot selection policy (P5.6 RC-027 Phase 6).

Design authority: PHYSICIAN_PILOT_POLICY.md. This is NOT the production priority model
(priority.py, which orders the general 9,153-task queue and is unchanged by this policy).
PHYSICIAN_PILOT_V1 governs ONLY the initial pilot-batch selection the owner explicitly
requested (2026-07-15): pediatric > pregnancy > renal > severe_allergy > missing_dose_or_
unit > unresolved_conflict > source_mismatch, with per-tier quotas so no single tier can
consume the whole batch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

POLICY_NAME = "PHYSICIAN_PILOT_V1"
POLICY_VERSION = 1

DOSE_ISSUE_TYPES = {"DOSE_NOT_EXTRACTED", "DOSE_NOT_PARSED", "DOSE_DAILY_MISREAD", "DOSE_UNIT_GROUP"}
CONFLICT_ISSUE_TYPES = {"CONFLICT_FIRST_LINE_DRUG", "CONFLICT_DOSE", "CONFLICT_DURATION"}

# Keyword fallback — used ONLY when the stored task carries no matching safety_axis/issue_type tag.
# Every match produced this way is labelled DERIVED_REVIEW_SIGNAL (never STORED), per Phase 6/7 —
# it is a review-time signal for pilot selection, never written back as a clinical fact.
_KEYWORD_PATTERNS = {
    "pediatric": re.compile(r"детск|ребен|ребён|педиатр|новорожд", re.IGNORECASE),
    "pregnancy": re.compile(r"беремен", re.IGNORECASE),
    "renal": re.compile(r"почеч|ренал|скф", re.IGNORECASE),
    "severe_allergy": re.compile(r"аллерг", re.IGNORECASE),
}

TIERS = [
    (1, "pediatric"),
    (2, "pregnancy"),
    (3, "renal"),
    (4, "severe_allergy"),
    (5, "missing_dose_or_unit"),
    (6, "unresolved_conflict"),
    (7, "source_mismatch"),
]


@dataclass(frozen=True)
class SignalMatch:
    tier: int
    label: str
    origin: str   # "STORED" | "DERIVED_REVIEW_SIGNAL"


def _text_blob(payload: dict) -> str:
    fields = ("indication", "therapeutic_class", "diagnosis", "age_group", "source_quote",
             "antibiotic", "selection_conditions")
    return " ".join(str(payload.get(f) or "") for f in fields)


def match_tiers(task, payload: dict) -> list[SignalMatch]:
    """Every tier the task matches, each tagged with its true origin (STORED vs derived-from-text).
    Never merges the two: a keyword-derived match is NEVER reported as a stored safety_axis."""
    text = _text_blob(payload)
    matches: list[SignalMatch] = []

    def add(tier: int, label: str, stored_cond: bool, keyword_key: str | None = None):
        if stored_cond:
            matches.append(SignalMatch(tier, label, "STORED"))
        elif keyword_key and _KEYWORD_PATTERNS[keyword_key].search(text):
            matches.append(SignalMatch(tier, label, "DERIVED_REVIEW_SIGNAL"))

    add(1, "pediatric", "pediatric" in task.safety_axes, "pediatric")
    add(2, "pregnancy", "pregnancy" in task.safety_axes, "pregnancy")
    add(3, "renal", "renal" in task.safety_axes, "renal")
    add(4, "severe_allergy", any("allerg" in a for a in task.safety_axes), "severe_allergy")
    add(5, "missing_dose_or_unit",
        "missing_unit" in task.safety_axes or task.issue_type in DOSE_ISSUE_TYPES)
    add(6, "unresolved_conflict",
        "clinical_conflict" in task.safety_axes or task.issue_type in CONFLICT_ISSUE_TYPES)
    add(7, "source_mismatch", "source_mismatch" in task.safety_axes)

    return matches


def primary_rank(task, payload: dict) -> tuple[int, str, str, int, str]:
    """(tier, label, origin, tie-break score, task_id) — best (lowest-numbered) tier wins."""
    matches = match_tiers(task, payload)
    if not matches:
        return (99, "no_owner_tier_match", "NONE", -task.priority_score, task.task_id)
    best = min(matches, key=lambda m: m.tier)
    return (best.tier, best.label, best.origin, -len(matches) - task.priority_score, task.task_id)


# Явная сила свидетельства внутри яруса. Раньше порядок задавался строковым сравнением
# поля origin, и «DERIVED_REVIEW_SIGNAL» < «STORED» просто потому, что D < S — то есть
# попадание по ключевому слову в свободном тексте обходило кураторскую сохранённую ось
# безопасности. Это противоречит PHYSICIAN_PILOT_POLICY.md: STORED берётся из реальных
# структурированных данных, а DERIVED_REVIEW_SIGNAL — регулярка, которая «может дать
# ложное срабатывание» и «не является клиническим утверждением».
_ORIGIN_RANK = {"STORED": 0, "DERIVED_REVIEW_SIGNAL": 1, "NONE": 2}


def _sort_key(pair: tuple) -> tuple:
    """Ключ сортировки: ярус, метка, СИЛА СВИДЕТЕЛЬСТВА, тай-брейк, task_id.

    Сила свидетельства подставлена явно, а не взята из строки origin, иначе порядок
    менялся бы от переименования константы.
    """
    rank = pair[0]
    return (rank[0], rank[1], _ORIGIN_RANK.get(rank[2], 99), rank[3], rank[4])


def select_quota_capped(scored: list[tuple], count: int) -> list:
    """scored: list of ((tier, label, origin, tiebreak, task_id), task), pre-sorted or not.
    Fills tier-by-tier with a cap = ceil(count / tiers_present) so one numerous tier cannot
    consume the whole batch (Phase 6 requirement: deterministic quotas)."""
    scored = sorted(scored, key=_sort_key)
    by_tier: dict[int, list] = {}
    for rank, t in scored:
        by_tier.setdefault(rank[0], []).append((rank, t))

    present_tiers = sorted(by_tier)
    n_tiers = len(present_tiers) or 1
    cap = max(1, -(-count // n_tiers))

    selected: list = []
    for tier in present_tiers:
        selected.extend(t for _, t in by_tier[tier][:cap])
        if len(selected) >= count:
            break
    if len(selected) < count:
        chosen_ids = {t.task_id for t in selected}
        for rank, t in scored:
            if t.task_id not in chosen_ids:
                selected.append(t)
                chosen_ids.add(t.task_id)
                if len(selected) >= count:
                    break
    return selected[:count]
