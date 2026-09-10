"""Tests for the physician review queue over block-level crosswalk links.

The queue ranks links by *structural* risk only. The two guarantees that matter:

1. **It never decides clinical relevance** — no category, severity or wording
   may claim a link is correct or wrong; the artifact stays PHYSICIAN_REVIEW_ONLY.
2. **It is deterministic and complete** — every ``ICD10_BLOCK`` link appears
   exactly once, the order is reproducible, and exact-code links are excluded.
"""

from __future__ import annotations

import json

import pytest

from clinical_engine.crosswalk import (
    AGE_DIRECTION_CONFLICT,
    BLOCK_ONLY_DISEASE,
    COARSE_SHARED_BLOCK,
    EXTERNAL_CAUSE_ONLY,
    METHOD_ICD10_BLOCK,
    METHOD_ICD10_EXACT,
    ROUTINE,
    build_review_queue,
    classify_link,
    to_issue_records,
)
from clinical_engine.crosswalk.builder import DEFAULT_CALCULATOR_DB, DEFAULT_DIAGNOSIS_INDEX
from clinical_engine.crosswalk.review_queue import DEFAULT_OUTPUT, main


def _link(disease_id, guideline_id, matched, title="КР", method=METHOD_ICD10_BLOCK, **extra):
    return {
        "disease_id": disease_id,
        "disease_name": disease_id.replace("_", " "),
        "cr_id": "1_1",
        "guideline_id": guideline_id,
        "guideline_title": title,
        "guideline_years": [2024],
        "matched_icd10": matched,
        "method": method,
        "confidence": "MEDIUM",
        "diagnosis_names": ["пример диагноза"],
        **extra,
    }


def _db(*rows):
    return {"recommendations": [{"id": disease, "age_groups": ages} for disease, ages in rows]}


# ── classification ──────────────────────────────────────────────────────────


def test_external_cause_code_is_the_loudest_signal():
    verdict = classify_link(_link("postop_prophylaxis", "1702", ["Y83.0"]))

    assert verdict["category"] == EXTERNAL_CAUSE_ONLY
    assert verdict["severity"] == "HIGH"
    assert "Y83.0" in verdict["flag_notes"][EXTERNAL_CAUSE_ONLY]


@pytest.mark.parametrize("code", ["V01.0", "W19", "X44.2", "Y83.0"])
def test_whole_chapter_xx_counts_as_external_cause(code):
    assert classify_link(_link("d", "1", [code]))["category"] == EXTERNAL_CAUSE_ONLY


def test_mixed_codes_are_not_flagged_as_external_cause():
    """Если есть настоящий код заболевания, связь держится на нём, а не на Y-коде."""

    verdict = classify_link(_link("d", "1", ["Y83.0", "M86.0"]))

    assert EXTERNAL_CAUSE_ONLY not in verdict["flags"]


@pytest.mark.parametrize(
    ("title", "age_groups", "conflict"),
    [
        ("Туберкулез у детей", ["adult"], True),
        ("Кампилобактериоз у детей", ["adult"], True),
        ("Пневмония у взрослых", ["child"], True),
        ("Туберкулез у детей", ["adult", "child"], False),
        ("Туберкулез у детей", ["all"], False),
        ("Туберкулез у детей", ["neonate"], False),
        ("Туберкулез у детей", [], False),
        ("Пневмония у взрослых", ["adult"], False),
        ("Острый синусит", ["adult"], False),
    ],
)
def test_age_direction_conflict(title, age_groups, conflict):
    verdict = classify_link(_link("d", "1", ["J01"], title=title), disease_age_groups=age_groups)

    assert (AGE_DIRECTION_CONFLICT in verdict["flags"]) is conflict


def test_block_only_disease_is_flagged():
    verdict = classify_link(_link("d", "1", ["J01"]), disease_has_exact_link=False)

    assert verdict["category"] == BLOCK_ONLY_DISEASE
    assert verdict["severity"] == "MEDIUM"


def test_coarse_shared_block_is_flagged():
    verdict = classify_link(_link("d", "1", ["J01"]), guideline_disease_count=4)

    assert verdict["category"] == COARSE_SHARED_BLOCK
    assert "4" in verdict["flag_notes"][COARSE_SHARED_BLOCK]


def test_a_link_without_signals_is_still_queued():
    """Блочная связь без структурных подозрений всё равно требует человека."""

    verdict = classify_link(_link("d", "1", ["J01"]))

    assert verdict["category"] == ROUTINE
    assert verdict["severity"] == "LOW"


def test_all_flags_are_kept_even_when_one_wins():
    verdict = classify_link(
        _link("d", "1", ["Y83.0"]),
        disease_age_groups=["adult"],
        disease_has_exact_link=False,
        guideline_disease_count=3,
    )

    assert verdict["category"] == EXTERNAL_CAUSE_ONLY
    assert set(verdict["flags"]) == {
        EXTERNAL_CAUSE_ONLY,
        BLOCK_ONLY_DISEASE,
        COARSE_SHARED_BLOCK,
    }
    assert len(verdict["flag_notes"]) == 3


def test_classification_never_claims_clinical_truth():
    verdict = classify_link(_link("d", "1", ["Y83.0"]))

    assert "severity" in verdict and "correct" not in verdict and "approved" not in verdict


# ── queue building ──────────────────────────────────────────────────────────


def test_queue_covers_every_block_link_exactly_once():
    crosswalk = {
        "content_sha256": "sha256:deadbeef",
        "links": [
            _link("a", "1", ["J01"]),
            _link("a", "2", ["J02"], method=METHOD_ICD10_EXACT),
            _link("b", "3", ["K35"]),
            _link("b", "4", ["K35"]),
        ],
    }

    report = build_review_queue(crosswalk, _db(("a", ["adult"]), ("b", ["adult"])))
    coverage = report["coverage"]

    assert coverage["block_links"] == 3
    assert coverage["exact_or_title_links_excluded"] == 1
    assert coverage["block_diseases"] == 2
    assert coverage["block_guidelines"] == 3
    assert len(report["queue"]) == 3
    assert len({row["queue_id"] for row in report["queue"]}) == 3


def test_shared_guideline_count_is_measured_from_the_artifact():
    crosswalk = {
        "links": [
            _link("a", "1702", ["A18"]),
            _link("b", "1702", ["A23"]),
            _link("c", "9999", ["J01"]),
        ]
    }

    report = build_review_queue(crosswalk, _db(("a", ["adult"]), ("b", ["adult"]), ("c", ["adult"])))
    by_id = {row["guideline_id"]: row for row in report["queue"]}

    assert COARSE_SHARED_BLOCK in by_id["1702"]["flags"]
    assert COARSE_SHARED_BLOCK not in by_id["9999"]["flags"]


def test_queue_is_sorted_by_severity_then_category_then_ids():
    # Точная связь дана aaa и zzz, но не mmm: только так три нозологии попадают
    # в три разные полосы — HIGH, MEDIUM и LOW.
    crosswalk = {
        "links": [
            _link("zzz", "0z", ["Z99.9"], method=METHOD_ICD10_EXACT),
            _link("aaa", "0a", ["A99.9"], method=METHOD_ICD10_EXACT),
            _link("zzz", "1", ["J01"]),
            _link("aaa", "2", ["Y83.0"]),
            _link("mmm", "3", ["K35"]),
        ]
    }

    report = build_review_queue(crosswalk, _db(("zzz", ["adult"]), ("aaa", ["adult"]), ("mmm", ["adult"])))
    order = [(row["severity"], row["category"], row["disease_id"]) for row in report["queue"]]

    assert order == [
        ("HIGH", EXTERNAL_CAUSE_ONLY, "aaa"),
        ("MEDIUM", BLOCK_ONLY_DISEASE, "mmm"),
        ("LOW", ROUTINE, "zzz"),
    ]


def test_queue_is_deterministic():
    crosswalk = {"links": [_link("a", "1", ["Y83.0"]), _link("b", "2", ["K35"])]}
    db = _db(("a", ["adult"]), ("b", ["adult"]))

    first = build_review_queue(crosswalk, db, generated_at="t")
    second = build_review_queue(crosswalk, db, generated_at="t")

    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(
        second, sort_keys=True, ensure_ascii=False
    )


def test_report_declares_review_only_and_keeps_source_hash():
    report = build_review_queue({"content_sha256": "sha256:abc", "links": []}, _db())

    assert report["meta"]["purpose"] == "PHYSICIAN_REVIEW_ONLY"
    assert report["meta"]["source_artifact_sha256"] == "sha256:abc"
    assert "NAVIGATION_ONLY" in report["meta"]["warning"]
    assert "НЕ решает" in report["meta"]["warning"]


def test_every_row_carries_the_question_and_never_a_verdict():
    crosswalk = {"links": [_link("a", "1", ["Y83.0"])]}

    row = build_review_queue(crosswalk, _db(("a", ["adult"])))["queue"][0]

    assert "?" in row["question_for_reviewer"]
    assert "решает врач" in row["decision_hint"]
    for forbidden in ("approved", "confirmed", "correct", "verified"):
        assert forbidden not in row["question_for_reviewer"].lower()


def test_missing_age_groups_does_not_invent_a_conflict():
    crosswalk = {"links": [_link("orphan", "1", ["J01"], title="Туберкулез у детей")]}

    report = build_review_queue(crosswalk, {"recommendations": []})

    assert AGE_DIRECTION_CONFLICT not in report["queue"][0]["flags"]


# ── review-store records ────────────────────────────────────────────────────


def test_issue_records_match_the_store_contract():
    crosswalk = {"links": [_link("a", "1", ["Y83.0"])]}
    report = build_review_queue(crosswalk, _db(("a", ["adult"])), generated_at="2026-09-11T00:00:00+00:00")

    records = to_issue_records(report)

    assert len(records) == 1
    record = records[0]
    # Required (non-defaulted) keys of ReviewStore.import_issue.
    for key in ("issue_id", "object_id", "object_type", "source", "category", "severity",
                "clinical_impact", "detected_by", "timestamp"):
        assert key in record and record[key]
    assert record["status"] == "PENDING"
    assert record["issue_id"] == "xwblock_a_1"
    assert record["page_cell_provenance"]["method"] == METHOD_ICD10_BLOCK


def test_issue_ids_are_stable_across_rebuilds():
    crosswalk = {"links": [_link("a", "1", ["Y83.0"])]}
    db = _db(("a", ["adult"]))

    first = [r["issue_id"] for r in to_issue_records(build_review_queue(crosswalk, db, generated_at="t1"))]
    second = [r["issue_id"] for r in to_issue_records(build_review_queue(crosswalk, db, generated_at="t2"))]

    assert first == second


# ── shipped artifact ────────────────────────────────────────────────────────


def test_committed_queue_matches_the_shipped_crosswalk():
    """Отгруженная очередь обязана соответствовать отгруженному артефакту."""
    if not DEFAULT_OUTPUT.is_file():
        pytest.skip("review queue artifact not generated")

    crosswalk = json.loads(DEFAULT_OUTPUT.parent.joinpath("calculator_crosswalk.json").read_text(encoding="utf-8"))
    db = json.loads(DEFAULT_CALCULATOR_DB.read_text(encoding="utf-8-sig"))
    report = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))

    expected = {
        (link["disease_id"], link["guideline_id"])
        for link in crosswalk["links"]
        if link["method"] == METHOD_ICD10_BLOCK
    }
    actual = {(row["disease_id"], row["guideline_id"]) for row in report["queue"]}

    assert actual == expected
    assert len(report["queue"]) == len(expected)
    assert report["meta"]["source_artifact_sha256"] == crosswalk["content_sha256"]
    assert report["coverage"]["block_links"] == len(expected)
    assert sum(report["coverage"]["by_category"].values()) == len(expected)
    assert sum(report["coverage"]["by_severity"].values()) == len(expected)


def test_cli_reports_without_writing(tmp_path, capsys):
    code = main(
        [
            "--crosswalk",
            "clinical_engine/resources/calculator_crosswalk.json",
            "--db",
            str(DEFAULT_CALCULATOR_DB),
            "--output",
            str(tmp_path / "unused.json"),
        ]
    )

    assert code == 0
    assert not (tmp_path / "unused.json").exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["coverage"]["block_links"] == payload["coverage"]["block_links"]
    assert payload["meta"]["purpose"] == "PHYSICIAN_REVIEW_ONLY"


def test_cli_writes_sorted_json_with_trailing_newline(tmp_path):
    out = tmp_path / "queue.json"

    assert main(["--db", str(DEFAULT_CALCULATOR_DB), "--output", str(out), "--write"]) == 0

    text = out.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    report = json.loads(text)
    assert report["coverage"]["block_links"] > 0
    assert json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n" == text
