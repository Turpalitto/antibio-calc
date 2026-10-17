"""Audit 2026-10-14 (I-4): the calculator and the Clinical Engine keep two drug
class tables — `DRUG_CLASSES` in `antibiotic_calc.html.template` (drives
`checkAllergyStatus`) and `allergy_class_hierarchy` in
`clinical_engine/resources/clinical_constants.json` (drives the hard safety
filter). They are not shared yet (the engine is NOT connected to the shell, and
merging them is an owner decision), so this test pins the only thing that is
safety-relevant today: both tables must agree on beta-lactam membership, and
every drug the calculator can actually dose must be known to the allergy check.

The calculator only reacts to three classes — penicillin*, cephalosporin* and
carbapenem; everything else is "safe" under the selectable allergies. A drug
missing from `DRUG_CLASSES` therefore degrades to "safe" silently, which is
exactly the failure mode this test makes loud.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "antibiotic_calc.html.template"
DB_PATH = ROOT / "db" / "antibio_db.json"
CONSTANTS = ROOT / "clinical_engine" / "resources" / "clinical_constants.json"

JS_BETA_LACTAM_FAMILY = {
    "penicillin": "Пенициллины",
    "cephalosporin": "Цефалоспорины",
    "carbapenem": "Карбапенемы",
}
ENGINE_BETA_LACTAM_CLASSES = set(JS_BETA_LACTAM_FAMILY.values())

# Drugs that appear only in BLOCKED records and are absent from the engine's
# hierarchy. They cannot be dosed by the calculator today; adding them to the
# engine table is a frozen-module/owner change, so they are listed here instead
# of being silently tolerated. Remove an entry once the owner adds the class.
KNOWN_BLOCKED_ONLY_GAPS_IN_ENGINE = {
    "netilmicin",
    "ofloxacin",
    "rifaximin",
    "tetracycline",
    "tinidazole",
    "tobramycin",
}


def _js_drug_classes() -> dict[str, str]:
    source = TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r"const DRUG_CLASSES = \{(.*?)\};", source, re.S)
    assert match, "DRUG_CLASSES literal not found in the template"
    pairs = re.findall(r"['\"]?([a-z0-9_]+)['\"]?\s*:\s*['\"]([a-z0-9_]+)['\"]", match.group(1))
    table = dict(pairs)
    assert len(table) == len(pairs), "duplicate keys in DRUG_CLASSES"
    return table


def _engine_classes() -> dict[str, str]:
    constants = json.loads(CONSTANTS.read_text(encoding="utf-8-sig"))
    hierarchy = constants["allergy_class_hierarchy"]
    table: dict[str, str] = {}
    for cls, drugs in hierarchy.items():
        for drug in drugs:
            assert drug not in table, f"{drug} listed under two engine classes"
            table[drug] = cls
    return table


def _db_drug_refs() -> tuple[set[str], set[str]]:
    """(refs used in computable records, refs used anywhere)."""
    db = json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    computable: set[str] = set()
    everywhere: set[str] = set()
    for record in db["recommendations"]:
        blocked = bool(record.get("calculation_blocked"))
        for scenario in record.get("scenarios", []):
            for line in scenario.get("lines", []):
                for drug in line.get("drugs", []):
                    refs = drug["combo_ref"] if "combo_ref" in drug else [drug["drug_ref"]]
                    everywhere.update(refs)
                    if not blocked:
                        computable.update(refs)
    return computable, everywhere


def _js_family(js_class: str) -> str | None:
    for prefix, family in JS_BETA_LACTAM_FAMILY.items():
        if js_class.startswith(prefix):
            return family
    return None


def test_every_computable_drug_is_known_to_the_calculator_allergy_check() -> None:
    computable, _ = _db_drug_refs()
    js = _js_drug_classes()
    missing = sorted(computable - set(js))
    assert not missing, (
        "drugs dosed by the calculator but absent from DRUG_CLASSES "
        f"(checkAllergyStatus would silently treat them as safe): {missing}"
    )


def test_every_computable_drug_is_known_to_the_engine_hierarchy() -> None:
    computable, everywhere = _db_drug_refs()
    engine = _engine_classes()
    missing_computable = sorted(computable - set(engine))
    assert not missing_computable, f"computable drugs missing from allergy_class_hierarchy: {missing_computable}"
    # Blocked-only gaps are tolerated but must stay documented above.
    blocked_only_gaps = (everywhere - computable) - set(engine)
    assert blocked_only_gaps == KNOWN_BLOCKED_ONLY_GAPS_IN_ENGINE, (
        "blocked-only drugs missing from the engine hierarchy changed — "
        f"update KNOWN_BLOCKED_ONLY_GAPS_IN_ENGINE: {sorted(blocked_only_gaps)}"
    )


def test_beta_lactam_membership_agrees_between_calculator_and_engine() -> None:
    js = _js_drug_classes()
    engine = _engine_classes()
    disagreements = []
    for drug in sorted(set(js) & set(engine)):
        js_family = _js_family(js[drug])
        engine_family = engine[drug] if engine[drug] in ENGINE_BETA_LACTAM_CLASSES else None
        if js_family != engine_family:
            disagreements.append((drug, js[drug], engine[drug]))
    assert not disagreements, f"beta-lactam classification differs: {disagreements}"


def test_no_beta_lactam_hides_under_a_non_beta_lactam_class() -> None:
    """A beta-lactam filed as 'other' would pass every allergy gate."""
    js = _js_drug_classes()
    engine = _engine_classes()
    beta_lactam_in_engine = {d for d, c in engine.items() if c in ENGINE_BETA_LACTAM_CLASSES}
    leaks = sorted(d for d in beta_lactam_in_engine if d in js and _js_family(js[d]) is None)
    assert not leaks, f"engine beta-lactams that the calculator treats as non-beta-lactam: {leaks}"
    # Name-based safety net for drugs the engine does not list yet.
    suspicious = sorted(
        d for d, c in js.items()
        if any(part in d for part in ("cillin", "cef", "ceph", "penem", "bactam")) and _js_family(c) is None
    )
    assert not suspicious, f"beta-lactam-looking keys with a non-beta-lactam class: {suspicious}"
