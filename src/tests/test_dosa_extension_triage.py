"""Tests for dosa_extension_triage (source-prover classification)."""

from __future__ import annotations

import json

from src.pipeline.extraction.dosa_extension_triage import build_triage


def _rec(id_: str, name: str, cr_id: str = "000_0") -> dict:
    return {"id": id_, "name": name, "cr_id": cr_id}


def test_infection_rule() -> None:
    t = build_triage([_rec("urogenitalnyi_trikhomoniaz", "Урогенитальный трихомониаз", "241_3")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("infection") == 1
    assert t["total"] == 1


def test_surgical_rule() -> None:
    t = build_triage([_rec("perelomy_taza", "Переломы проксимального отдела бедренной кости", "980_1")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("surgical_prophylaxis") == 1


def test_oncology_rule() -> None:
    t = build_triage([_rec("ostryi_limfoblastnyi_leikoz", "Острые миелоидные лейкозы", "586_3")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("oncology") == 1


def test_congenital_cardiac_rule() -> None:
    t = build_triage([_rec("trekhpredserdnoe_serdtse", "Трехпредсердное сердце", "772_1")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("congenital_cardiac_prophylaxis") == 1


def test_immunodeficiency_pjp_rule() -> None:
    t = build_triage([_rec("sistemnyi_skleroz", "Системный склероз", "607_1")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("immunodeficiency_pjp") == 1


def test_metabolic_genetic_rule() -> None:
    t = build_triage([_rec("kistoznyi_fibroz", "Кистозный фиброз (муковисцидоз)", "372_3")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("metabolic_genetic") == 1


def test_override_applied() -> None:
    # pnevmotsistnaia_pnevmoniia = ВИЧ -> PJP prophylaxis (overrides infection rule).
    t = build_triage([_rec("pnevmotsistnaia_pnevmoniia", "ВИЧ-инфекция у взрослых", "79_2")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("immunodeficiency_pjp") == 1
    assert cats.get("infection") is None


def test_typo_fix_gidradenit() -> None:
    t = build_triage([_rec("gidradenit_gnoinyi", "Гидраденит гнойный", "963_1")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("infection") == 1


def test_orbital_fracture_is_surgical() -> None:
    t = build_triage([_rec("perelom_dna_glaznitsy", "Перелом дна глазницы", "652_2")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("surgical_prophylaxis") == 1


def test_amanitin_override_real_id() -> None:
    t = build_triage([_rec("otravlenie_gribami_soderzhashchimi_amanitin", "Отравление грибами, содержащими аманитин", "926_1")])
    cats = {c["key"]: len(c["records"]) for c in t["categories"]}
    assert cats.get("infection") == 1


def test_never_hints_unblock() -> None:
    t = build_triage([_rec("x", "Урогенитальный трихомониаз", "241_3")])
    assert t["artifact_type"] == "DOSA_EXTENSION_TRIAGE"
    assert "PASSED" not in json.dumps(t)
    assert "calculation_blocked" in json.dumps(t)
