"""Read-only curation validator + progress reporter (P3 support).

Reports progress toward PRODUCTION_CURATED WITHOUT writing the curated index.
Reuses the SAME validation rules as build_curated_index (imported, not
reimplemented) so this report can never disagree with the actual build.

Makes NO clinical decision. It only checks that each physician decision in the
ledger is well-formed and attributed, and summarises how far the physician has
progressed.

Exit code: 0 if the ledger would produce PRODUCTION_CURATED (0 pending, 0
invalid), else 1 — suitable as a CI / pre-deploy gate.

Usage (from repo root):
    python -m clinical_engine.tools.validate_curation \
        [--ledger diagnosis_index_decisions.json] \
        [--out-md diagnosis_index_curation_progress.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from clinical_engine.tools.build_curated_index import _validate

_DEFAULT_LEDGER = "diagnosis_index_decisions.json"
_DEFAULT_MD = "diagnosis_index_curation_progress.md"


def validate(ledger_path: str) -> dict:
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    decisions = ledger.get("decisions", [])

    pending: list[str] = []
    invalid: list[dict] = []
    valid: list[dict] = []
    by_decision: Counter = Counter()

    for rec in decisions:
        decision = rec.get("decision", "pending_review")
        by_decision[decision] += 1
        if decision == "pending_review":
            pending.append(rec.get("diagnosis", ""))
            continue
        err = _validate(rec)
        if err:
            invalid.append({"diagnosis": rec.get("diagnosis", ""),
                            "conflict_id": rec.get("conflict_id", ""),
                            "decision": decision, "error": err})
        else:
            valid.append(rec)

    total = len(decisions)
    resolved = len(valid)
    production_ready = (len(pending) == 0 and len(invalid) == 0 and total > 0)
    pct = round(100.0 * resolved / total, 1) if total else 0.0

    return {
        "ledger": ledger_path,
        "total": total,
        "resolved": resolved,
        "pending": len(pending),
        "invalid": len(invalid),
        "by_decision": dict(by_decision),
        "invalid_decisions": invalid,
        "pending_diagnoses": sorted(pending),
        "percent_resolved": pct,
        "would_be_status": "PRODUCTION_CURATED" if production_ready else "PARTIALLY_CURATED",
        "production_ready": production_ready,
    }


def render_md(r: dict) -> str:
    bar_len = 30
    filled = int(bar_len * r["percent_resolved"] / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    lines = [
        "# diagnosis_index — Curation Progress",
        "",
        "> Read-only. Uses the same validation rules as `build_curated_index`. "
        "No clinical decision is made here.",
        "",
        f"`{bar}` **{r['percent_resolved']}%** ({r['resolved']}/{r['total']} resolved)",
        "",
        f"- Would-be status: **{r['would_be_status']}**",
        f"- Pending: **{r['pending']}** · Invalid: **{r['invalid']}** · Resolved: **{r['resolved']}**",
        f"- Decisions by type: {r['by_decision']}",
        "",
    ]
    if r["invalid_decisions"]:
        lines += ["## ⚠️ Invalid decisions (block production — fix attribution/fields)", ""]
        lines += ["| Diagnosis | Decision | Error |", "|---|---|---|"]
        for d in r["invalid_decisions"]:
            lines.append(f"| {d['diagnosis']} | {d['decision']} | {d['error']} |")
        lines.append("")
    if not r["production_ready"]:
        lines.append("**NOT production-ready.** Physician must resolve all pending "
                     "and fix all invalid decisions in `diagnosis_index_decisions.json`.")
    else:
        lines.append("**Production-ready.** Run `build_curated_index` to emit PRODUCTION_CURATED.")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    ap.add_argument("--out-md", default=_DEFAULT_MD)
    args = ap.parse_args()
    r = validate(args.ledger)
    Path(args.out_md).write_text(render_md(r), encoding="utf-8")
    print("=== curation progress ===")
    print(f"resolved {r['resolved']}/{r['total']} ({r['percent_resolved']}%)  "
          f"pending {r['pending']}  invalid {r['invalid']}")
    print(f"would-be status: {r['would_be_status']}")
    print(f"written: {args.out_md}")
    sys.exit(0 if r["production_ready"] else 1)


if __name__ == "__main__":
    main()
