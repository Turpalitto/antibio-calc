"""Physician worklist + mechanical triage for diagnosis_index conflicts (P3-1 support).

READ-ONLY. Renders the decision ledger (build_decision_ledger.py) into a
review-friendly worklist so a physician can resolve conflicts efficiently.

This tool NEVER proposes or makes a clinical decision. It only:
  - lists each unresolved conflict with the facts a physician needs
    (diagnosis, competing guideline_ids, ICD codes, titles, source URLs);
  - attaches a purely *lexical / structural* triage hint to help the
    physician prioritise. The hint is derived only from string overlap and
    ICD-code set shape — it contains no medical knowledge and must not be
    read as a recommended answer.

Triage hint vocabulary (mechanical, non-clinical):
  NAME_TITLE_DISJOINT  the diagnosis name shares no word with ANY option's
                       title AND the ICD sets differ -> the auto-extraction
                       likely mismapped this row (physician: probably none of
                       these / find the correct guideline). Highest priority.
  LIKELY_DUPLICATE     every option has the same ICD set and same title
                       -> physician may confirm a duplicate.
  ICD_DIVERGENT        options have disjoint ICD-code sets.
  ICD_OVERLAP          options share at least one ICD code.
  REVIEW               none of the above patterns detected.

Usage (from repo root):
    python -m clinical_engine.tools.build_conflict_worklist \
        [--ledger diagnosis_index_decisions.json] \
        [--out-md diagnosis_index_worklist.md] \
        [--out-csv diagnosis_index_worklist.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

_DEFAULT_LEDGER = "diagnosis_index_decisions.json"
_DEFAULT_MD = "diagnosis_index_worklist.md"
_DEFAULT_CSV = "diagnosis_index_worklist.csv"

# Lexical-only stopwords (Russian connective/anatomical filler + generic
# clinical qualifiers). Used solely to reduce trivial token-overlap noise in
# the triage hint. Not a medical mapping.
_STOPWORDS = {
    "и", "или", "с", "у", "при", "для", "по", "на", "в", "во", "от", "до",
    "острый", "острая", "острое", "хронический", "хроническая", "хроническое",
    "взрослых", "детей", "у_взрослых", "у_детей", "форма", "стадия", "степень",
    "неуточненный", "неуточнённый", "другой", "прочий",
}

_WORD_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    toks = {t.lower() for t in _WORD_RE.findall(text)}
    return {t for t in toks if len(t) >= 4 and t not in _STOPWORDS}


def _icd_set(option: dict) -> frozenset[str]:
    return frozenset(str(c).strip().upper() for c in (option.get("icd10") or []) if str(c).strip())


def triage_hint(rec: dict) -> str:
    """Purely lexical/structural priority hint. No clinical judgement."""
    options = rec.get("guideline_options", []) or []
    if len(options) < 2:
        return "REVIEW"

    dx_tokens = _tokens(rec.get("diagnosis"))
    title_tokens: set[str] = set()
    for o in options:
        title_tokens |= _tokens(o.get("title"))
    shares_word = bool(dx_tokens & title_tokens)

    icd_sets = [_icd_set(o) for o in options]
    titles = {(o.get("title") or "").strip().lower() for o in options}
    all_same_icd = len({s for s in icd_sets}) == 1
    union = set().union(*icd_sets) if icd_sets else set()
    pairwise_disjoint = sum(len(s) for s in icd_sets) == len(union)

    if not shares_word and not all_same_icd:
        return "NAME_TITLE_DISJOINT"
    if all_same_icd and len(titles) == 1:
        return "LIKELY_DUPLICATE"
    if pairwise_disjoint:
        return "ICD_DIVERGENT"
    return "ICD_OVERLAP"


def build(ledger_path: str, out_md: str, out_csv: str) -> dict:
    ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    decisions = ledger.get("decisions", [])

    rows: list[dict] = []
    for rec in decisions:
        status = rec.get("decision", "pending_review")
        options = rec.get("guideline_options", []) or []
        rows.append({
            "conflict_id": rec.get("conflict_id", ""),
            "diagnosis": rec.get("diagnosis", ""),
            "severity": rec.get("severity", ""),
            "conflict_type": rec.get("conflict_type", ""),
            "status": status,
            "triage_hint": triage_hint(rec),
            "n_options": len(options),
            "guideline_ids": ";".join(str(o.get("guideline_id", "")) for o in options),
            "titles": " || ".join(str(o.get("title", "")) for o in options),
            "icd10": " || ".join(",".join(o.get("icd10") or []) for o in options),
            "decided_by": rec.get("decided_by") or "",
            "decision": status,
        })

    # Priority order for the physician: disjoint-name first, then by severity.
    hint_rank = {"NAME_TITLE_DISJOINT": 0, "ICD_DIVERGENT": 1, "ICD_OVERLAP": 2,
                 "LIKELY_DUPLICATE": 3, "REVIEW": 4}
    sev_rank = {"CRITICAL": 0, "MEDIUM": 1, "SAFE": 2}
    rows.sort(key=lambda r: (r["status"] != "pending_review",
                             hint_rank.get(r["triage_hint"], 9),
                             sev_rank.get(r["severity"], 9),
                             r["diagnosis"]))

    # CSV
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                           ["conflict_id", "diagnosis", "severity", "conflict_type",
                            "status", "triage_hint", "n_options", "guideline_ids",
                            "titles", "icd10", "decided_by", "decision"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Markdown
    hint_counts = Counter(r["triage_hint"] for r in rows if r["status"] == "pending_review")
    sev_counts = Counter(r["severity"] for r in rows if r["status"] == "pending_review")
    pending = sum(1 for r in rows if r["status"] == "pending_review")

    lines = [
        "# diagnosis_index — Physician Conflict Worklist",
        "",
        "> Generated by `build_conflict_worklist.py`. **Triage hints are lexical/structural only "
        "and are NOT clinical recommendations.** Every decision is the physician's, recorded in "
        "`diagnosis_index_decisions.json` with `decided_by` / `decided_at` / `rationale`.",
        "",
        f"- Total conflicts: **{len(rows)}** · Pending: **{pending}** · Resolved: **{len(rows) - pending}**",
        f"- Pending by triage hint: {dict(hint_counts)}",
        f"- Pending by severity: {dict(sev_counts)}",
        "",
        "How to decide each row: see `PHYSICIAN_VALIDATION_GUIDE.md` (decision vocabulary: "
        "`keep_all_complementary` / `select_primary` / `duplicate_keep_one` / `split` / `remove_diagnosis`).",
        "",
        "| # | Triage (lexical) | Sev | Diagnosis | Options (guideline_id · ICD · title) | Status |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        opt_cells = []
        gids = r["guideline_ids"].split(";") if r["guideline_ids"] else []
        titles = r["titles"].split(" || ") if r["titles"] else []
        icds = r["icd10"].split(" || ") if r["icd10"] else []
        for j, gid in enumerate(gids):
            t = titles[j] if j < len(titles) else ""
            ic = icds[j] if j < len(icds) else ""
            opt_cells.append(f"`{gid}` · {ic} · {t}")
        opts = "<br>".join(opt_cells)
        status_icon = "⬜ pending" if r["status"] == "pending_review" else f"✅ {r['status']}"
        lines.append(f"| {i} | {r['triage_hint']} | {r['severity']} | {r['diagnosis']} | {opts} | {status_icon} |")
    Path(out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "ledger": ledger_path, "out_md": out_md, "out_csv": out_csv,
        "total": len(rows), "pending": pending,
        "by_hint": dict(hint_counts), "by_severity": dict(sev_counts),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    ap.add_argument("--out-md", default=_DEFAULT_MD)
    ap.add_argument("--out-csv", default=_DEFAULT_CSV)
    args = ap.parse_args()
    r = build(args.ledger, args.out_md, args.out_csv)
    print("=== physician conflict worklist ===")
    print(f"conflicts: {r['total']}  pending: {r['pending']}")
    print(f"triage (pending): {r['by_hint']}")
    print(f"severity (pending): {r['by_severity']}")
    print(f"written: {r['out_md']} , {r['out_csv']}")
    print("NOTE: triage hints are lexical only — physician makes every clinical decision.")


if __name__ == "__main__":
    main()
