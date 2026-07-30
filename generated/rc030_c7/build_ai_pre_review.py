"""Build the C7 AI pre-review companion.

This artifact is advisory only. It must never be accepted as OWNER_LOCAL,
human validation, clinical approval, or calculation eligibility.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dose_verification_sandbox.verdict_taxonomy import HUMAN_FIDELITY_VERDICTS


INPUT = ROOT / "generated" / "rc030_c7" / "review_tasks_ready.json"
OUTPUT = ROOT / "RC030_C7_AI_PRE_REVIEW_EVENTS.json"

RANGE_DAILY_IDS = {
    "5659",
    "5683",
    "5998",
    "6133",
    "7895",
    # Every UNIT_BASIS_REVIEW record below has an explicit daily-total marker.
    "5364", "5441", "5442", "5678", "5696", "5727", "5741", "5875",
    "5917", "5918", "5928", "6042", "6073", "6075", "6085", "6110",
    "6111", "6303", "6305", "6579", "6580", "6638", "6989", "6990",
    "7017", "7022", "7026", "7031", "7036", "7042", "7043", "7051",
    "7059", "7064", "7069", "7497", "7498", "7519", "7520", "7629",
    "7630", "7644", "7645",
}

WRONG_DOSE_ANCHOR_IDS = {"5528"}

VISUAL_TABLE_IDS = {
    "5623", "5628", "5683", "6756", "6761",
    "6766", "6771", "6799", "6804", "7895",
}
VISUAL_PDF_IDS = {"5475", "5726", "6068"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verdict(regimen_id: str) -> str:
    if regimen_id in WRONG_DOSE_ANCHOR_IDS:
        return "WRONG_DOSE_ANCHOR"
    if regimen_id in RANGE_DAILY_IDS:
        return "CORRECT_RANGE_DAILY"
    return "CORRECT_RANGE_SINGLE"


def _note(task: dict, verdict: str) -> str:
    regimen_id = str(task["regimen_id"])
    if verdict == "WRONG_DOSE_ANCHOR":
        return (
            "The 15-20 mg/kg range belongs to ethambutol; the target rifabutin "
            "dose is 5 mg/kg once daily. The candidate range crosses a drug anchor."
        )
    if regimen_id in {"5683", "7895"}:
        return (
            "Visual PDF review confirmed that the table header is 'Суточные дозы "
            "для детей'; 50-80 mg/kg is therefore a daily-total range."
        )
    if regimen_id in {
        "5623", "5628", "6756", "6761", "6766", "6771", "6799", "6804"
    }:
        return (
            "Visual PDF table review confirmed clindamycin 0.6-0.9 g as an "
            "alternative prophylaxis dose; the notes column states that PAP is "
            "administered once (with a <=24 h exception for contaminated surgery)."
        )
    if regimen_id == "6068":
        return (
            "Visual PDF review confirmed 500¹-1000² mg: superscript footnote "
            "markers were flattened by extraction; the clinical range is "
            "500-1000 mg three times daily, per administration."
        )
    if regimen_id == "5726":
        return (
            "Visual PDF review distinguishes the pre-operative 1.0 g dose from "
            "the 0.5-1.0 g intra/post-operative doses every 6-8 h; frequency=4 "
            "links the candidate range to the latter per-administration regimen."
        )
    if regimen_id == "5475":
        return (
            "Visual PDF review confirmed the source wording 25-50 mg/kg once "
            "daily for three days and the printed 125 mg maximum. This is source "
            "fidelity only; clinical appropriateness was not adjudicated."
        )
    if verdict == "CORRECT_RANGE_DAILY":
        return (
            "The source explicitly marks the range as a daily total ('/сут', "
            "'в сутки', or 'в день'), with any administrations stated as divisions."
        )
    return (
        "The source ties the range to one administration through an explicit "
        "frequency, interval, per-infusion/per-administration marker, or one-time use."
    )


def build() -> dict:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    events = []
    for task in tasks:
        regimen_id = str(task["regimen_id"])
        verdict = _verdict(regimen_id)
        if verdict not in HUMAN_FIDELITY_VERDICTS:
            raise ValueError(f"unknown verdict for {regimen_id}: {verdict}")
        evidence_quality = (
            "VISUAL_TABLE"
            if regimen_id in VISUAL_TABLE_IDS
            else "VISUAL_PDF"
            if regimen_id in VISUAL_PDF_IDS
            else "DIRECT_QUOTE_AND_CONTEXT"
        )
        events.append(
            {
                "ai_event_id": f"ai-c7-pre-review-{regimen_id}",
                "audit_version": 1,
                "created_at": "2026-07-29T00:00:00Z",
                "regimen_id": regimen_id,
                "regimen_version": task["regimen_version"],
                "unit_id": task["unit_id"],
                "queue_category": task["queue_category"],
                "final_ai_verdict": verdict,
                "ai_note": _note(task, verdict),
                "exact_evidence_quote": task["exact_quote"],
                "pdf": task["source_pdf_relative_path"],
                "page": task["page"],
                "pdf_hash": task["PDF_hash"],
                "source_packet_hash": task["source_packet_hash"],
                "parser_candidate": task["deterministic_classification"],
                "parser_agreement": (
                    "AI_NONCONFIRMING"
                    if verdict == "WRONG_DOSE_ANCHOR"
                    else "AI_CONFIRMING"
                ),
                "confidence": (
                    "HIGH_VISUAL"
                    if evidence_quality.startswith("VISUAL")
                    else "HIGH_EXPLICIT"
                ),
                "evidence_quality": evidence_quality,
                "risk_flags": task["risk_flags"],
                "review_origin": "AI_PRE_REVIEW",
                "owner_verified": False,
                "human_validated": False,
                "clinically_approved": False,
                "calculation_eligibility": "BLOCKED",
                "test_event": False,
            }
        )

    result = {
        "schema_version": 1,
        "review_origin": "AI_PRE_REVIEW",
        "generated_at": "2026-07-29T00:00:00Z",
        "input_path": str(INPUT.relative_to(ROOT)).replace("\\", "/"),
        "input_sha256": _sha256(INPUT),
        "count": len(events),
        "events": events,
    }
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def validate(result: dict) -> None:
    tasks = json.loads(INPUT.read_text(encoding="utf-8"))["tasks"]
    task_ids = {str(task["regimen_id"]) for task in tasks}
    events = result["events"]
    event_ids = {event["regimen_id"] for event in events}
    if len(tasks) != 113 or len(events) != 113:
        raise ValueError(f"expected 113 tasks/events, got {len(tasks)}/{len(events)}")
    if task_ids != event_ids:
        raise ValueError("AI pre-review coverage differs from the C7 ready queue")
    if len(event_ids) != len(events):
        raise ValueError("duplicate regimen_id in AI pre-review")
    for event in events:
        if event["review_origin"] != "AI_PRE_REVIEW":
            raise ValueError("review origin drift")
        if event["owner_verified"] or event["human_validated"] or event["clinically_approved"]:
            raise ValueError("AI event falsely claims human or clinical validation")
        if event["calculation_eligibility"] != "BLOCKED":
            raise ValueError("AI event must remain calculation-blocked")
        if event["final_ai_verdict"] not in HUMAN_FIDELITY_VERDICTS:
            raise ValueError("unknown canonical verdict")


if __name__ == "__main__":
    built = build()
    validate(built)
    counts: dict[str, int] = {}
    for event in built["events"]:
        verdict = event["final_ai_verdict"]
        counts[verdict] = counts.get(verdict, 0) + 1
    print(json.dumps({"count": built["count"], "verdicts": counts}, ensure_ascii=False))
