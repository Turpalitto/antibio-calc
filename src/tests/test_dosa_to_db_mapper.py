"""Tests for src/pipeline/extraction/dosa_to_db_mapper.py (source-prover mapper).

These verify the DOSA klinrec -> db/diseases record mapping in isolation:
drug-reference resolution (markers, Russian de-inflection, composites, group
names), Cyrillic slug transliteration, and honest coverage counting. The mapper
is a *source prover* only: it must never emit an unregistered drug_ref (the db
validator would fail) and must never hint that a disease is unblocked.
"""

from __future__ import annotations

import pytest

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


def test_parse_age_is_none_for_unstated_age() -> None:
    """L-12: an unstated age must NOT silently read as 'adult'.

    Returning 'adult' put 'adult' into every guideline's `age_groups` and made
    `scenario_bindings._linkage` stamp GUIDELINE_SCOPE_ADULT on child-only data.
    """
    assert m._parse_age("") is None
    assert m._parse_age(None) is None
    assert m._parse_age("   ") is None
    assert m._parse_age("общая схема") is None


def test_child_only_guideline_does_not_advertise_adult() -> None:
    kb = [{
        "code_version": "281_3",
        "guideline_name": "Инфекция мочевых путей",
        "diagnosis": "Инфекция мочевых путей",
        "mkb": ["N39.0"],
        "regimens": [_regimen("амоксициллин**", age="дети 3-12 мес")],
    }]
    out = m.build_mapped_db(kb, {"281_3"})
    rec = out["recommendations"][0]
    assert rec["age_groups"] == ["child"]
    assert all(sc["age_group"] == "child" for sc in rec["scenarios"])


def _regimen(drug: str, *, rt: str = "first_line", age: str = "взрослые",
             dose: str = "0,5", unit: str = "г", freq: str = "2 раза в день",
             duration: str | None = None) -> dict:
    return {
        "antibiotic": drug,
        "dose": dose,
        "unit": unit,
        "frequency": freq,
        "route": "внутрь",
        "duration": duration,
        "age_group": age,
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


# ---------------------------------------------------------------------------
# C-2 -- dose BASIS must be parsed, not guessed.  A per-dose amount written into
# a *_day field is a 3x underdose for a TID regimen.
# ---------------------------------------------------------------------------

def test_c2_gram_dose_is_per_dose_not_per_day() -> None:
    """"1 г" x3/day is 1000 mg PER DOSE, 3000 mg/day -- never dose_mg_day_fixed=1000."""
    out = m._normalize_dose("1", "г", 3)
    assert "dose_mg_day_fixed" not in out, "per-dose value leaked into a per-day field"
    assert out["single_dose_mg"] == 1000.0
    assert out["dose_basis"] == "per_dose"
    assert out["max_daily_mg"] == 3000.0


def test_c2_gram_dose_latin_unit_is_per_dose() -> None:
    out = m._normalize_dose("1", "g", 3)
    assert out["single_dose_mg"] == 1000.0
    assert out["max_daily_mg"] == 3000.0


@pytest.mark.parametrize("unit", ["мг/кг/введение", "мг/кг/раз", "мг/кг/инфуз", "мг/кг"])
def test_c2_weight_per_dose_never_lands_in_day_field(unit: str) -> None:
    """"7 мг/кг/введение" x3 is per-dose; writing it as dose_mg_kg_day said 7/day."""
    out = m._normalize_dose("7", unit, 3)
    assert "dose_mg_kg_day" not in out, f"{unit} leaked a per-dose value into dose_mg_kg_day"
    assert out["dose_mg_kg_per_dose"] == 7.0
    assert out["dose_basis"] == "per_dose"


@pytest.mark.parametrize("unit", ["мг/кг/сут", "мг/кг/сутки", "мг/кг/день", "mg/kg/day"])
def test_c2_weight_per_day_forms_still_fill_the_day_field(unit: str) -> None:
    out = m._normalize_dose("30", unit, 3)
    assert out["dose_mg_kg_day"] == 30.0
    assert "dose_mg_kg_per_dose" not in out
    assert out["dose_basis"] == "per_day"


def test_c2_explicit_per_day_fixed_dose_uses_the_day_field() -> None:
    out = m._normalize_dose("250 мг/сут", "", 1)
    assert out["dose_mg_day_fixed"] == 250.0
    assert out["dose_basis"] == "per_day"
    assert out["max_daily_mg"] == 250.0


def test_c2_dose_text_denominator_beats_bare_unit_column() -> None:
    """"1 г/сут" against a unit column of "г" is a DAILY dose."""
    out = m._normalize_dose("1 г/сут", "г", 1)
    assert out["dose_mg_day_fixed"] == 1000.0
    assert out["dose_basis"] == "per_day"


def test_c2_range_is_recorded_not_truncated() -> None:
    """"500-1000 мг" x3/day: base 500, ceiling 3000 -- the old code reported 1500."""
    out = m._normalize_dose("500-1000", "мг", 3)
    assert out["single_dose_mg"] == 500.0
    assert out["single_dose_mg_max"] == 1000.0
    assert out["max_daily_mg"] == 3000.0
    assert out["dose_range_wording"] == "500-1000"


def test_c2_range_with_leading_decimal_and_late_unit() -> None:
    out = m._normalize_dose("0,5-1 г", "", 3)
    assert out["single_dose_mg"] == 500.0
    assert out["single_dose_mg_max"] == 1000.0
    assert out["max_daily_mg"] == 3000.0


def test_c2_weight_range_is_recorded() -> None:
    out = m._normalize_dose("50-60", "мг/кг/сут", 2)
    assert out["dose_mg_kg_day"] == 50.0
    assert out["dose_mg_kg_day_max"] == 60.0


def test_c2_escalation_takes_the_max_and_records_it() -> None:
    out = m._normalize_dose("500 мг, затем 1 г", "", 3)
    assert out["single_dose_mg_max"] == 1000.0
    assert out["dose_escalated"] is True
    assert out["max_daily_mg"] == 3000.0


def test_c2_escalation_keeps_the_starting_dose_as_the_base() -> None:
    out = m._normalize_dose("500 мг, затем 1000 мг", "", 3)
    assert out["single_dose_mg"] == 500.0
    assert out["single_dose_mg_max"] == 1000.0
    assert out["dose_escalated"] is True


@pytest.mark.parametrize(("dose", "unit"), [("500", "мл"), ("2", "МЕ"), ("1", "таблетка")])
def test_c2_non_mass_dose_returns_empty_and_fails_closed(dose: str, unit: str) -> None:
    assert m._normalize_dose(dose, unit, 3) == {}


def test_c2_bare_number_without_unit_is_not_a_dose() -> None:
    assert m._normalize_dose("7", "", 3) == {}


# ---------------------------------------------------------------------------
# H-25 -- a regimen with NO usable dose must never reach the patient-facing DB.
# ---------------------------------------------------------------------------

def test_h25_regimen_without_dose_is_dropped_with_a_reason() -> None:
    notes: list[dict] = []
    rec = m.map_guideline(
        {"code_version": "911_1", "guideline_name": "Метронидазол", "mkb": ["A05.1"]},
        [
            _regimen("метронидазол**", dose="500", unit="мл", duration="5 дней"),
            _regimen("амоксициллин**", dose="500", unit="мг"),
        ],
        notes=notes,
    )
    assert [d["drug_ref"] for sc in rec["scenarios"] for ln in sc["lines"] for d in ln["drugs"]] == [
        "amoxicillin"
    ]
    assert [n["reason"] for n in notes] == ["no_usable_dose"]
    assert notes[0]["drug_ref"] == "metronidazole"


def test_h25_regimen_with_no_dose_field_at_all_is_dropped() -> None:
    notes: list[dict] = []
    rec = m.map_guideline(
        {"code_version": "911_2", "guideline_name": "Метронидазол", "mkb": ["A05.1"]},
        [_regimen("метронидазол**", dose="", unit="", duration="5 дней")],
        notes=notes,
    )
    assert rec["scenarios"] == []
    assert [n["reason"] for n in notes] == ["no_usable_dose"]


def test_skip_notes_record_unresolvable_drug_and_frequency() -> None:
    notes: list[dict] = []
    m.map_guideline(
        {"code_version": "999_9", "guideline_name": "T", "mkb": []},
        [
            _regimen("фторхинолоны"),
            _regimen("амоксициллин**", freq="в соответствии с инструкцией"),
        ],
        notes=notes,
    )
    assert {n["reason"] for n in notes} == {"unresolvable_drug", "frequency_not_determined"}


# ---------------------------------------------------------------------------
# C-3 -- adult and child regimens must NOT be merged into one scenario.
# ---------------------------------------------------------------------------

def test_c3_adult_and_child_regimens_produce_separate_scenarios() -> None:
    """A child mg/kg regimen must never sit inside an 'adult' scenario."""
    rec = m.map_guideline(
        {"code_version": "714_2", "guideline_name": "Внебольничная пневмония", "mkb": ["J18.9"]},
        [
            _regimen("амоксициллин**", age="взрослые", dose="500", unit="мг"),
            _regimen("амоксициллин**", age="дети", dose="50", unit="мг/кг/сут", freq="2 раза в день"),
        ],
    )
    assert {sc["age_group"] for sc in rec["scenarios"]} == {"adult", "child"}
    by_age = {sc["age_group"]: sc for sc in rec["scenarios"]}
    adult_regimen = by_age["adult"]["lines"][0]["drugs"][0]["regimens"][0]
    child_regimen = by_age["child"]["lines"][0]["drugs"][0]["regimens"][0]
    assert adult_regimen["single_dose_mg"] == 500.0
    assert "dose_mg_kg_day" not in adult_regimen
    assert child_regimen["dose_mg_kg_day"] == 50.0
    assert "single_dose_mg" not in child_regimen
    # Scenario ids must be unique -- scenario_bindings looks a scenario up by id.
    assert len({sc["id"] for sc in rec["scenarios"]}) == 2


def test_c3_single_age_keeps_the_historical_scenario_id() -> None:
    rec = m.map_guideline(
        {"code_version": "654_2", "guideline_name": "ВП у взрослых", "mkb": ["J18.9"]},
        [_regimen("амоксициллин**", age="взрослые")],
    )
    assert [sc["id"] for sc in rec["scenarios"]] == ["first_line_line"]


def test_c3_same_line_two_drugs_same_age_share_one_scenario() -> None:
    rec = m.map_guideline(
        {"code_version": "654_3", "guideline_name": "ВП", "mkb": ["J18.9"]},
        [
            _regimen("амоксициллин**", age="взрослые"),
            _regimen("цефтриаксон**", age="взрослые", dose="1", unit="г"),
        ],
    )
    assert len(rec["scenarios"]) == 1
    drugs = rec["scenarios"][0]["lines"][0]["drugs"]
    assert {d["drug_ref"] for d in drugs} == {"amoxicillin", "ceftriaxone"}


# ---------------------------------------------------------------------------
# H-26 -- duration_days must hold days; the quote must live in a read field.
# ---------------------------------------------------------------------------

def test_h26_duration_days_holds_numbers_and_quote_lives_in_source_quote() -> None:
    rec = m.map_guideline(
        {"code_version": "999_7", "guideline_name": "T", "mkb": []},
        [_regimen("амоксициллин**", duration="7-10 дней")],
    )
    scheme = rec["scenarios"][0]["lines"][0]["drugs"][0]["regimens"][0]
    assert scheme["duration_days"] == 7
    assert scheme["duration_days_max"] == 10
    assert scheme["duration_text"] == "7-10 дней"
    assert scheme["source_quote"] == "Цитата про амоксициллин**."
    assert "duration_note" not in scheme


def test_h26_empty_duration_is_empty_not_free_text() -> None:
    rec = m.map_guideline(
        {"code_version": "999_8", "guideline_name": "T", "mkb": []},
        [_regimen("амоксициллин**", duration=None)],
    )
    scheme = rec["scenarios"][0]["lines"][0]["drugs"][0]["regimens"][0]
    assert scheme["duration_days"] == ""
    assert "duration_text" not in scheme


# ---------------------------------------------------------------------------
# L-9 / L-11
# ---------------------------------------------------------------------------

def test_l9_multi_ending_russian_forms_resolve() -> None:
    """"метронидазола" strips two endings; one strip left no nominative."""
    stems = m._de_inflect("метронидазола")
    assert "метронидазол" in stems


def test_l11_source_url_is_never_a_dangling_fragment() -> None:
    rec = m.map_guideline({"code_version": "", "guideline_name": "T", "mkb": []}, [])
    assert rec["source_url"] == ""


def test_l11_approval_year_is_read_from_the_payload() -> None:
    rec = m.map_guideline(
        {"code_version": "9_3", "guideline_name": "T", "mkb": [], "cr_year": 2024},
        [_regimen("амоксициллин**")],
    )
    assert rec["cr_year"] == 2024
    assert rec["cr_updated"] == 2024


def test_l11_explicit_source_url_wins() -> None:
    rec = m.map_guideline(
        {"code_version": "9_3", "guideline_name": "T", "mkb": [],
         "source_url": "https://example.test/cr/9_3"},
        [_regimen("амоксициллин**")],
    )
    assert rec["source_url"] == "https://example.test/cr/9_3"


def test_build_mapped_db_reports_skip_reasons() -> None:
    kb = [{
        "code_version": "911_1",
        "guideline_name": "Метронидазол",
        "diagnosis": "Метронидазол",
        "mkb": ["A05.1"],
        "regimens": [_regimen("метронидазол**", dose="500", unit="мл")],
    }]
    out = m.build_mapped_db(kb, {"911_1"})
    assert out["skipped"] == [
        {**out["skipped"][0], "code_version": "911_1", "reason": "no_usable_dose"}
    ]
    assert out["recommendations"] == []
