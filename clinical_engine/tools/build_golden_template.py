"""Golden Case template generator (P3-7 support).

Emits a Golden Case *skeleton* for a curated diagnosis with every CLINICAL
expectation left BLANK. It never fills a drug, dose, route, therapy line,
exclusion, or trace expectation — those require the physician's explicit review
against the Russian Clinical Guideline and approval (`physician_review`).

Output filename is prefixed with '_' so the golden runner / guard tests treat
it as infrastructure (not an executable case) until a physician fills the
`expect` block and renames it (drop the leading '_').

The template documents the dimensions P3-7 requires proof for — routing,
first-line, alternatives, allergy, pediatric, pregnancy, renal — as review
checkboxes, all defaulting to unreviewed/false.

Usage (from repo root):
    python -m clinical_engine.tools.build_golden_template \
        --diagnosis "Эпиглоттит" --icd10 J05.1 \
        [--guideline-id 1832] [--out-dir clinical_engine/golden_cases]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_DEFAULT_OUT_DIR = "clinical_engine/golden_cases"


_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _slug(text: str) -> str:
    lowered = "".join(_TRANSLIT.get(ch, ch) for ch in text.lower())
    s = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return s or "case"


def make_template(diagnosis: str, icd10: str | None, guideline_id: str | None) -> dict:
    """Skeleton with NO clinical values. `expect` empty -> not an executable
    case until a physician fills it (runner treats empty-expect as FAIL)."""
    return {
        "id": f"diagnosis_{_slug(diagnosis)}_TEMPLATE",
        "description": (
            f"TEMPLATE for '{diagnosis}'. Physician must fill `expect` from the "
            "Russian Clinical Guideline and set physician_review.*=true, then "
            "remove the leading '_' from the filename to activate."
        ),
        "query": {
            "diagnosis": diagnosis,
            "icd10": icd10,
            "patient": {
                "age": None, "weight_kg": None, "pregnant": False,
                "renal_function": None, "hepatic_impairment": False,
                "allergies": [], "current_meds": [],
            },
            "preferences": {"therapy_line": None, "route_preference": None, "population": None},
        },
        # EMPTY by design. Physician adds only guideline-verified assertions,
        # e.g. "guideline_id", "first_drug_normalized", "not_guideline_id",
        # "excluded_drug_refs", "safety_flag_codes", "trace_code". See runner.py.
        "expect": {},
        "physician_review": {
            "routing": {"approved": False, "expected_guideline_id": guideline_id, "notes": ""},
            "first_line": {"approved": False, "expected_drug": None, "notes": ""},
            "alternatives": {"approved": False, "expected_drugs": [], "notes": ""},
            "allergy_handling": {"applicable": None, "approved": False, "notes": ""},
            "pediatric": {"applicable": None, "approved": False, "notes": ""},
            "pregnancy": {"applicable": None, "approved": False, "notes": ""},
            "renal": {"applicable": None, "approved": False, "notes": ""},
        },
        "provenance": {
            "author": "",              # physician name — REQUIRED before activation
            "verified_at": "",         # ISO timestamp — REQUIRED
            "guideline_id": guideline_id,
            "guideline_source_url": "",  # cr.minzdrav.gov.ru/recomend/<id>
            "source": "TEMPLATE — not physician-verified yet",
        },
    }


def build(diagnosis: str, icd10: str | None, guideline_id: str | None, out_dir: str) -> dict:
    doc = make_template(diagnosis, icd10, guideline_id)
    out = Path(out_dir) / f"_{_slug(diagnosis)}_template.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"out": str(out), "id": doc["id"], "expect_is_empty": doc["expect"] == {}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnosis", required=True)
    ap.add_argument("--icd10", default=None)
    ap.add_argument("--guideline-id", default=None)
    ap.add_argument("--out-dir", default=_DEFAULT_OUT_DIR)
    args = ap.parse_args()
    r = build(args.diagnosis, args.icd10, args.guideline_id, args.out_dir)
    print("=== golden template (clinical fields BLANK) ===")
    print(f"written: {r['out']}")
    print(f"id:      {r['id']}")
    print("NOTE: expect{} is empty — physician fills guideline-verified assertions, "
          "sets physician_review.*, adds provenance.author, then drops the leading '_'.")


if __name__ == "__main__":
    main()
