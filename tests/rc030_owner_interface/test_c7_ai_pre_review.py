import json
from pathlib import Path

from generated.rc030_c7.build_ai_pre_review import INPUT, OUTPUT, build, validate


ROOT = Path(__file__).resolve().parents[2]


def test_c7_ai_pre_review_is_complete_and_never_impersonates_owner():
    result = build()
    validate(result)

    assert result["review_origin"] == "AI_PRE_REVIEW"
    assert result["count"] == 113
    assert len({event["regimen_id"] for event in result["events"]}) == 113
    assert all(event["review_origin"] == "AI_PRE_REVIEW" for event in result["events"])
    assert all(event["owner_verified"] is False for event in result["events"])
    assert all(event["human_validated"] is False for event in result["events"])
    assert all(event["clinically_approved"] is False for event in result["events"])
    assert all(
        event["calculation_eligibility"] == "BLOCKED"
        for event in result["events"]
    )


def test_c7_ai_pre_review_covers_exact_ready_queue_and_expected_findings():
    result = build()
    tasks = json.loads(INPUT.read_text(encoding="utf-8"))["tasks"]
    events = {event["regimen_id"]: event for event in result["events"]}

    assert set(events) == {str(task["regimen_id"]) for task in tasks}
    assert events["5528"]["final_ai_verdict"] == "WRONG_DOSE_ANCHOR"
    assert events["5683"]["final_ai_verdict"] == "CORRECT_RANGE_DAILY"
    assert events["5683"]["evidence_quality"] == "VISUAL_TABLE"
    assert events["6068"]["final_ai_verdict"] == "CORRECT_RANGE_SINGLE"
    assert events["6068"]["evidence_quality"] == "VISUAL_PDF"
    assert OUTPUT.exists()
