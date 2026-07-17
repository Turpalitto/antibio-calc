"""RC-030 C6.8 Part VI Phase 11 -- replay all 365 range candidates through
the repaired engine (DoseUnitSignature-based compatibility, hardened
quote-matching regex additions). Read-only against generated/rc030_c68/
pass_a_365_input.json (frozen, hashed). No PDF opened, no DB write.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dose_verification_sandbox.span_attribution import attribute, normalize_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
IN_PATH = ROOT / "generated" / "rc030_c68" / "pass_a_365_input.json"
OUT_PATH = ROOT / "generated" / "rc030_c68" / "replay_365_results.json"
OLD_PATH = ROOT / "generated" / "rc030_multiworkstream" / "replay_with_unit_fix_365.json"


def main() -> None:
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    old_full_results = json.loads(OLD_PATH.read_text(encoding="utf-8"))["results"]
    old_results = {(r["regimen_id"], r["regimen_version"]): r["classification"] for r in old_full_results}

    # C6.8 methodology note: `needs_review_reasons` does not reliably encode
    # whether a record's source_quote is table-derived (verified directly --
    # several records classified AMBIGUOUS_TABLE_CONTEXT in the frozen C6.7
    # result have no "table" substring anywhere in needs_review_reasons, and
    # no committed table-detection signal exists elsewhere in the schema).
    # table_context is a structural fact about the source document (is this
    # text a table cell), not a safety verdict -- reusing the frozen C6.7
    # table-context set as an INPUT reconstruction aid is legitimate (same
    # category as reusing source_pdf/page/quote), unlike reusing a
    # SAFE/AMBIGUOUS classification itself, which is never done here.
    original_table_context_ids = {r["regimen_id"] for r in old_full_results
                                   if r["classification"] == "AMBIGUOUS_TABLE_CONTEXT"}

    results = []
    for r in data["records"]:
        table_flag = r["regimen_id"] in original_table_context_ids
        norm = normalize_text(r["source_quote"] or "")
        result = attribute(
            normalized=norm.normalized,
            known_antibiotic_raw=r["antibiotic"],
            current_scalar=r["dose"],
            current_unit=r["unit"],
            table_context=table_flag,
        )
        key = (r["regimen_id"], r["version"])
        old_classification = old_results.get((r["regimen_id"], r["version"]))
        entry = {
            "regimen_id": r["regimen_id"],
            "regimen_version": r["version"],
            "c67_classification": old_classification,
            "c68_classification": result.classification,
            "changed": old_classification != result.classification,
            "unit_compatibility": result.score_components.get("unit_compatibility") if result.score_components else None,
        }
        results.append(entry)

    from collections import Counter
    c68_counts = Counter(r["c68_classification"] for r in results)
    c67_counts = Counter(r["c67_classification"] for r in results)
    changed = [r for r in results if r["changed"]]

    out = {
        "schema_version": 1,
        "total": len(results),
        "c67_classification_counts": dict(c67_counts),
        "c68_classification_counts": dict(c68_counts),
        "changed_count": len(changed),
        "changed_records": changed,
        "all_results": results,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("C6.7 counts:", dict(c67_counts))
    print("C6.8 counts:", dict(c68_counts))
    print("changed:", len(changed))
    for r in changed:
        print(" ", r["regimen_id"], r["c67_classification"], "->", r["c68_classification"], "unit_compat=", r["unit_compatibility"])


if __name__ == "__main__":
    main()
