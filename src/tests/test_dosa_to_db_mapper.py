"""Tests for src/pipeline/extraction/dosa_to_db_mapper.py (source-prover mapper).

These verify the DOSA klinrec -> db/diseases record mapping in isolation:
drug-reference resolution (markers, Russian de-inflection, composites, group
names), Cyrillic slug transliteration, and honest coverage counting. The mapper
is a *source prover* only: it must never emit an unregistered drug_ref (the db
validator would fail) and must never hint that a disease is unblocked.
"""

from __future__ import annotations

from src.pipeline.extraction import dosa_to_db_mapper as m


def test_resolve_drug_ref_strips_markers_and_maps() -> None:
    assert m.resolve_drug_ref("цефтриаксон**") == "ceftriaxone"
    assert m.resolve_drug_ref("#ципрофлоксацин**") == "ciprofloxacin"
    assert m.resolve_drug_ref("метронидазол**") == "metronidazole"


def test_resolve_drug_ref_de_inflect_flexion() -> None:
    assert m.resolve_drug_ref("амоксициллина**") == "amoxicillin"
    assert m.resolve_drug_ref("цефотаксима**") == "cefotaxime"
    assert m.resolve_drug_ref("клиндамицина**") == "clindamycin"
    assert m.resolve_drug_ref("левофлоксацином**") == "levofloxacin"
    # tetracycline is now registered in drugs_reference -> resolves.
    assert m.resolve_drug_ref("#тетрациклина**") == "tetracycline"


def test_resolve_drug_ref_composite() -> None:
    assert m.resolve_drug_ref("Амоксициллин+Клавулановая кислота**") == "amoxiclav"
    assert m.resolve_drug_ref("Амоксициллин + [Клавулановая кислота]**") == "amoxiclav"
    assert m.resolve_drug_ref("#Пиперациллин+[Тазобактам] +/- #амикацин**") == "piperacillin_tazobactam"
    assert m.resolve_drug_ref("ампициллин+[Сульбактам]**") == "ampicillin"


def test_resolve_drug_ref_skips_group_names() -> None:
    assert m.resolve_drug_ref("фторхинолоны") is None
    assert m.resolve_drug_ref("макролиды") is None
    assert m.resolve_drug_ref("Другие бета-лактамные...") is None
    assert m.resolve_drug_ref("цефалоспорины") is None
    assert m.resolve_drug_ref("") is None


def test_slug_transliterates_cyrillic_unique() -> None:
    slug_a = m._slug("Брюшной тиф у взрослых")
    slug_b = m._slug("Острый аппендицит")
    slug_c = m._slug("Туберкулез у детей")
    assert slug_a != "nosology"
    assert slug_a != slug_b != slug_c
    assert slug_a == "briushnoi_tif_u_vzroslykh"
    assert slug_b == "ostryi_appenditsit"
    assert slug_c == "tuberkulez_u_detei"


def test_parse_age_mapping() -> None:
    assert m._parse_age("новорожденные") == "neonate"
    assert m._parse_age("дети") == "child"
    assert m._parse_age("взрослые") == "adult"
    assert m._parse_age("беременные") == "adult"
    assert m._parse_age("") == "adult"


def _regimen(drug: str, *, rt: str = "first_line") -> dict:
    return {
        "antibiotic": drug,
        "dose": "0,5",
        "unit": "г",
        "frequency": "2 раза в день",
        "route": "внутрь",
        "duration": None,
        "age_group": "взрослые",
        "regimen_type": rt,
        "source_quote": f"Цитата про {drug}.",
    }


def test_map_guideline_never_emits_unregistered_drug_ref() -> None:
    guideline = {"code_version": "999_1", "guideline_name": "Тестовая инфекция", "mkb": ["A00.0"]}
    regs = [
        _regimen("амоксициллин**"),
        _regimen("фторхинолоны"),  # group -> must be dropped
        _regimen("орнидазол"),  # unregistered -> must be dropped
    ]
    rec = m.map_guideline(guideline, regs)
    assert rec["cr_id"] == "999_1"
    drug_refs = {
        d["drug_ref"] for sc in rec["scenarios"] for ln in sc["lines"] for d in ln["drugs"]
    }
    assert drug_refs == {"amoxicillin"}
    # never an unregistered ref
    kb = {"amoxicillin", "amoxiclav", "ciprofloxacin", "ceftriaxone"}
    assert drug_refs <= kb


def test_build_mapped_db_honest_counts() -> None:
    kb = [
        {
            "code_version": "999_1",
            "guideline_name": "Тестовая инфекция",
            "diagnosis": "Тестовая инфекция",
            "mkb": ["A00.0"],
            "regimens": [
                _regimen("амоксициллин**"),
                _regimen("фторхинолоны"),
            ],
        }
    ]
    out = m.build_mapped_db(kb, {"999_1"})
    assert out["total_symbols"] == 2
    assert out["mapped_symbols"] == 1  # seulement amoxicillin mapped
    assert out["skipped_drug"] == 1
    assert len(out["recommendations"]) == 1
    rec = out["recommendations"][0]
    drug_refs = {d["drug_ref"] for sc in rec["scenarios"] for ln in sc["lines"] for d in ln["drugs"]}
    assert drug_refs == {"amoxicillin"}


def test_parse_freq_word_numerals_and_daily_idioms() -> None:
    assert m.parse_freq("2 раза в день") == 2
    assert m.parse_freq("два раза в день") == 2
    assert m.parse_freq("в сутки") == 1
    assert m.parse_freq("ежедневно") == 1
    assert m.parse_freq("в два приема") == 2
    assert m.parse_freq("однократно") == 1
    assert m.parse_freq("затем один раз в день") == 1
    assert m.parse_freq("None") is None
    assert m.parse_freq("") is None
    assert m.parse_freq(None) is None


def test_build_mapped_db_drops_regimen_with_unparseable_freq() -> None:
    kb = [
        {
            "code_version": "911_1",
            "guideline_name": "Ботулизм",
            "diagnosis": "Ботулизм",
            "mkb": ["A05.1"],
            "regimens": [
                _regimen("метронидазол**"),
                {
                    "antibiotic": "метронидазол**",
                    "dose": "0,5",
                    "unit": "г",
                    "frequency": "в соответствии с инструкцией",
                    "route": "внутрь",
                    "duration": None,
                    "age_group": "взрослые",
                    "regimen_type": "first_line",
                    "section_name": "x",
                    "source_quote": "q",
                },
            ],
        }
    ]
    out = m.build_mapped_db(kb, {"911_1"})
    assert len(out["recommendations"]) == 1
    for sc in out["recommendations"][0]["scenarios"]:
        for ln in sc["lines"]:
            for d in ln["drugs"]:
                for reg in d["regimens"]:
                    assert reg["freq_per_day"] is not None
