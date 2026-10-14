"""Clinical diff between two builds of `db/antibio_db.json` (audit 2026-10-14, I-6).

Medical software needs an answer to "what changed in the data between these
two builds?" that a physician can read. This tool compares two DB files (or a
git revision against the working tree) and reports, per nosology:

  * records added / removed;
  * record-level changes: `calculation_blocked`, `source_verification_status`,
    `cr_id`, `cr_year`, `name`, `age_groups`, `mkb10`;
  * scenario / line / drug changes (added, removed, route changed);
  * regimen changes field by field (`dose_mg_kg_day`, `dose_mg_kg_per_dose`,
    `dose_mg_day_fixed`, `single_dose_mg`, `freq_per_day`, `max_daily_mg`,
    `duration_days`), keyed by scenario → line → drug → regimen age group;
  * drug-reference changes (keys whose value changed), e.g. a new
    `concentration_mg_per_ml` or `age_restriction_min`.

Usage
    python db/db_diff.py --git 1885894                 # that revision vs working tree
    python db/db_diff.py old.json new.json             # two files
    python db/db_diff.py --git main --json             # machine-readable
    python db/db_diff.py --git main --markdown >> CHANGELOG_DB.md

Exit code 0 always (it is a report, not a gate); `--fail-on-change` returns 3
when anything differs, for scripts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_REL = "db/antibio_db.json"
DB_PATH = PROJECT_ROOT / DB_REL

RECORD_FIELDS = ("name", "cr_id", "cr_year", "calculation_blocked",
                 "source_verification_status", "age_groups", "mkb10")
REGIMEN_FIELDS = ("dose_mg_kg_day", "dose_mg_kg_per_dose", "dose_mg_day_fixed",
                  "single_dose_mg", "freq_per_day", "max_daily_mg", "duration_days")


# ── loading ──────────────────────────────────────────────────────────────────

def load_db_text(text: str) -> dict[str, Any]:
    data = json.loads(text.lstrip("\ufeff"))
    if not isinstance(data, dict) or "recommendations" not in data:
        raise ValueError("not an antibio DB: missing `recommendations`")
    return data


def load_db_file(path: Path) -> dict[str, Any]:
    return load_db_text(path.read_text(encoding="utf-8-sig"))


def load_db_git(revision: str, rel: str = DB_REL, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "show", f"{revision}:{rel}"], cwd=root, capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"git show {revision}:{rel} failed: {completed.stderr.strip()}")
    return load_db_text(completed.stdout)


# ── indexing ─────────────────────────────────────────────────────────────────

def _records(db: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in db.get("recommendations", []) if isinstance(r, dict) and "id" in r}


def _regimen_key(regimen: dict[str, Any], seen: dict[str, int]) -> str:
    """Stable key inside a drug: age group, de-duplicated by order of appearance."""
    group = str(regimen.get("age_group") or "?")
    seen[group] = seen.get(group, 0) + 1
    return group if seen[group] == 1 else f"{group}#{seen[group]}"


def _flatten_drugs(record: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """(scenario id, line number, drug_ref[#n]) → drug node with regimen index."""
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for scenario in record.get("scenarios", []) or []:
        sid = str(scenario.get("id") or scenario.get("name") or "?")
        for line in scenario.get("lines", []) or []:
            lnum = str(line.get("line_number", "?"))
            seen_refs: dict[str, int] = {}
            for drug in line.get("drugs", []) or []:
                ref = str(drug.get("drug_ref") or drug.get("inn") or "?")
                seen_refs[ref] = seen_refs.get(ref, 0) + 1
                key_ref = ref if seen_refs[ref] == 1 else f"{ref}#{seen_refs[ref]}"
                seen_groups: dict[str, int] = {}
                regimens = {
                    _regimen_key(reg, seen_groups): {f: reg.get(f) for f in REGIMEN_FIELDS}
                    for reg in drug.get("regimens", []) or []
                }
                out[(sid, lnum, key_ref)] = {"route": list(drug.get("route") or []), "regimens": regimens}
    return out


def _fmt_key(key: tuple[str, str, str]) -> str:
    sid, lnum, ref = key
    return f"{sid} / line {lnum} / {ref}"


# ── diff ─────────────────────────────────────────────────────────────────────

def diff_db(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_recs, new_recs = _records(old), _records(new)
    report: dict[str, Any] = {
        "summary": {},
        "records_added": sorted(set(new_recs) - set(old_recs)),
        "records_removed": sorted(set(old_recs) - set(new_recs)),
        "records_changed": [],
        "drugs_reference_changed": [],
    }
    for rid in sorted(set(old_recs) & set(new_recs)):
        o, n = old_recs[rid], new_recs[rid]
        entry: dict[str, Any] = {"id": rid, "name": n.get("name") or o.get("name"),
                                 "fields": {}, "drugs_added": [], "drugs_removed": [],
                                 "routes_changed": [], "regimens": []}
        for f in RECORD_FIELDS:
            if o.get(f) != n.get(f):
                entry["fields"][f] = {"old": o.get(f), "new": n.get(f)}
        od, nd = _flatten_drugs(o), _flatten_drugs(n)
        entry["drugs_added"] = [_fmt_key(k) for k in sorted(set(nd) - set(od))]
        entry["drugs_removed"] = [_fmt_key(k) for k in sorted(set(od) - set(nd))]
        for key in sorted(set(od) & set(nd)):
            if od[key]["route"] != nd[key]["route"]:
                entry["routes_changed"].append({"drug": _fmt_key(key), "old": od[key]["route"],
                                                "new": nd[key]["route"]})
            oreg, nreg = od[key]["regimens"], nd[key]["regimens"]
            for g in sorted(set(oreg) | set(nreg)):
                if g not in oreg:
                    entry["regimens"].append({"drug": _fmt_key(key), "age_group": g, "change": "added",
                                              "new": nreg[g]})
                elif g not in nreg:
                    entry["regimens"].append({"drug": _fmt_key(key), "age_group": g, "change": "removed",
                                              "old": oreg[g]})
                else:
                    changed = {f: {"old": oreg[g][f], "new": nreg[g][f]}
                               for f in REGIMEN_FIELDS if oreg[g][f] != nreg[g][f]}
                    if changed:
                        entry["regimens"].append({"drug": _fmt_key(key), "age_group": g,
                                                  "change": "changed", "fields": changed})
        if entry["fields"] or entry["drugs_added"] or entry["drugs_removed"] \
                or entry["routes_changed"] or entry["regimens"]:
            report["records_changed"].append(entry)

    o_drugs = old.get("drugs_reference") or {}
    n_drugs = new.get("drugs_reference") or {}
    for dk in sorted(set(o_drugs) | set(n_drugs)):
        if dk.startswith("_"):
            continue
        if dk not in o_drugs:
            report["drugs_reference_changed"].append({"drug": dk, "change": "added"})
        elif dk not in n_drugs:
            report["drugs_reference_changed"].append({"drug": dk, "change": "removed"})
        else:
            keys = sorted(k for k in set(o_drugs[dk]) | set(n_drugs[dk])
                          if o_drugs[dk].get(k) != n_drugs[dk].get(k))
            if keys:
                report["drugs_reference_changed"].append({"drug": dk, "change": "changed", "keys": keys})

    def _count_blocked(db: dict[str, Any]) -> int:
        return sum(1 for r in db.get("recommendations", []) if r.get("calculation_blocked"))

    report["summary"] = {
        "old_records": len(old_recs), "new_records": len(new_recs),
        "old_blocked": _count_blocked(old), "new_blocked": _count_blocked(new),
        "records_added": len(report["records_added"]),
        "records_removed": len(report["records_removed"]),
        "records_changed": len(report["records_changed"]),
        "regimen_changes": sum(len(e["regimens"]) for e in report["records_changed"]),
        "blocked_now": sorted(e["id"] for e in report["records_changed"]
                              if e["fields"].get("calculation_blocked", {}).get("new") is True),
        # true → false is a clinical unblock; a missing key made explicit is not
        "unblocked_now": sorted(e["id"] for e in report["records_changed"]
                                if e["fields"].get("calculation_blocked", {}).get("old") is True
                                and e["fields"].get("calculation_blocked", {}).get("new") is False),
        "block_flag_made_explicit": sorted(
            e["id"] for e in report["records_changed"]
            if "calculation_blocked" in e["fields"]
            and e["fields"]["calculation_blocked"].get("old") is None),
        "drugs_reference_changed": len(report["drugs_reference_changed"]),
    }
    report["changed"] = bool(report["records_added"] or report["records_removed"]
                             or report["records_changed"] or report["drugs_reference_changed"])
    return report


# ── rendering ────────────────────────────────────────────────────────────────

def _v(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value


def render_markdown(report: dict[str, Any], *, old_label: str, new_label: str) -> str:
    s = report["summary"]
    lines = [
        f"### DB diff: `{old_label}` → `{new_label}`",
        "",
        f"- records: {s['old_records']} → {s['new_records']} "
        f"(+{s['records_added']} / −{s['records_removed']}), changed: {s['records_changed']}",
        f"- blocked: {s['old_blocked']} → {s['new_blocked']}; "
        f"newly blocked: {len(s['blocked_now'])}; newly unblocked: {len(s['unblocked_now'])}",
        f"- regimen changes: {s['regimen_changes']}; drug-reference entries changed: "
        f"{s['drugs_reference_changed']}",
    ]
    if s["unblocked_now"]:
        lines.append(f"- **UNBLOCKED (owner attention):** {', '.join(s['unblocked_now'])}")
    if s["blocked_now"]:
        lines.append(f"- blocked now: {', '.join(s['blocked_now'])}")
    if s["block_flag_made_explicit"]:
        lines.append(f"- `calculation_blocked` made explicit (was missing): "
                     f"{', '.join(s['block_flag_made_explicit'])}")
    if report["records_added"]:
        lines.append(f"- added: {', '.join(report['records_added'])}")
    if report["records_removed"]:
        lines.append(f"- removed: {', '.join(report['records_removed'])}")
    for entry in report["records_changed"]:
        detail: list[str] = []
        for f, ch in entry["fields"].items():
            detail.append(f"{f}: {_v(ch['old'])} → {_v(ch['new'])}")
        for d in entry["drugs_added"]:
            detail.append(f"+ drug {d}")
        for d in entry["drugs_removed"]:
            detail.append(f"− drug {d}")
        for rc in entry["routes_changed"]:
            detail.append(f"route {rc['drug']}: {_v(rc['old'])} → {_v(rc['new'])}")
        for rg in entry["regimens"]:
            if rg["change"] == "changed":
                fields = ", ".join(f"{f} {_v(c['old'])} → {_v(c['new'])}" for f, c in rg["fields"].items())
                detail.append(f"regimen {rg['drug']} [{rg['age_group']}]: {fields}")
            else:
                payload = {k: v for k, v in (rg.get("new") or rg.get("old") or {}).items() if v is not None}
                detail.append(f"regimen {rg['drug']} [{rg['age_group']}] {rg['change']}: {_v(payload)}")
        lines.append(f"- **{entry['id']}** ({entry['name']}):")
        lines.extend(f"  - {d}" for d in detail)
    for d in report["drugs_reference_changed"]:
        if d["change"] == "changed":
            lines.append(f"- drug ref **{d['drug']}**: {', '.join(d['keys'])}")
        else:
            lines.append(f"- drug ref **{d['drug']}**: {d['change']}")
    if not report["changed"]:
        lines.append("- no clinical data changes")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clinical diff between two antibio_db.json builds")
    parser.add_argument("paths", nargs="*", help="OLD NEW json files (omit with --git)")
    parser.add_argument("--git", metavar="REV", help="compare REV:db/antibio_db.json with the working tree")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--markdown", action="store_true", help="markdown (default)")
    parser.add_argument("--fail-on-change", action="store_true", help="exit 3 when anything differs")
    args = parser.parse_args(argv)

    try:
        if args.git:
            if args.paths:
                parser.error("--git takes no positional paths")
            old, new = load_db_git(args.git), load_db_file(DB_PATH)
            old_label, new_label = f"{args.git}:{DB_REL}", DB_REL
        elif len(args.paths) == 2:
            old, new = load_db_file(Path(args.paths[0])), load_db_file(Path(args.paths[1]))
            old_label, new_label = args.paths
        else:
            parser.error("give OLD NEW or --git REV")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"db_diff: {exc}", file=sys.stderr)
        return 2

    report = diff_db(old, new)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_markdown(report, old_label=old_label, new_label=new_label))
    return 3 if (args.fail_on_change and report["changed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
