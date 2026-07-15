from antibiotic_gate import gate_one


def test_gate_high_confidence_drugs():
    item = {
        "Name": "Внебольничная пневмония",
        "CodeVersion": "123_6",
        "Mkbs": [{"MkbCode": "J18", "MkbName": "Пневмония"}],
    }
    text = "Антибактериальная терапия: амоксициллин 500 мг 3 раза в день 7 дней. Цефтриаксон 1 г внутривенно."
    result = gate_one(item, text)

    assert result["status"] == "process"
    assert result["antibiotic_probability"] >= 70
    assert "амоксициллин" in result["matched_drugs"]
    assert result["reason"] == "high_confidence_antibiotics"


def test_gate_high_confidence_section():
    item = {
        "Name": "Острый пиелонефрит",
        "CodeVersion": "9_3",
        "Mkbs": [{"MkbCode": "N10"}],
    }
    text = "Антибактериальная терапия назначается при остром пиелонефрите. Ципрофлоксацин 500 мг 2 раза в день."
    result = gate_one(item, text)

    assert result["status"] == "process"
    assert result["antibiotic_probability"] >= 70
    assert "ципрофлоксацин" in result["matched_drugs"]


def test_gate_medium_confidence_keywords():
    item = {
        "Name": "Ринит острый",
        "CodeVersion": "55_1",
        "Mkbs": [{"MkbCode": "J00"}],
    }
    text = "Острый ринит вирусной этиологии. Бактериальный ринит встречается редко. Инфекция верхних дыхательных путей."
    result = gate_one(item, text)

    assert result["status"] in ("review", "process")
    assert result["antibiotic_probability"] >= 25


def test_gate_skip_no_antibiotics():
    item = {
        "Name": "Глаукома",
        "CodeVersion": "77_2",
        "Mkbs": [{"MkbCode": "H40"}],
    }
    text = "Глаукома — заболевание глаз. Снижение внутриглазного давления. Симптоматическое лечение."
    result = gate_one(item, text)

    assert result["status"] == "skip"
    assert result["antibiotic_probability"] < 30
    assert result["reason"] == "low_confidence_no_antibiotics"


def test_gate_icd_match_only():
    item = {
        "Name": "Неизвестное заболевание",
        "CodeVersion": "99_1",
        "Mkbs": [{"MkbCode": "J15"}],
    }
    text = "Неизвестное заболевание. Описание симптомов."
    result = gate_one(item, text)

    assert result["matched_icd"] == ["J15"]
    assert result["antibiotic_probability"] >= 10


def test_gate_empty_item():
    item = {"Name": "", "CodeVersion": "", "Mkbs": []}
    result = gate_one(item, "")

    assert result["status"] == "skip"
    assert result["antibiotic_probability"] == 0


def test_gate_multiple_drugs():
    item = {
        "Name": "Сепсис",
        "CodeVersion": "41_1",
        "Mkbs": [{"MkbCode": "A41"}],
    }
    text = "амоксициллин цефтриаксон ванкомицин меропенем линезолид антибактериальная терапия"
    result = gate_one(item, text)

    assert result["status"] == "process"
    assert len(result["matched_drugs"]) >= 4
    assert result["antibiotic_probability"] >= 80


def test_gate_sepsis_icd():
    item = {
        "Name": "Сепсис",
        "CodeVersion": "41_1",
        "Mkbs": [{"MkbCode": "A41"}],
    }
    text = "Сепсис. Тяжёлое состояние."
    result = gate_one(item, text)

    assert "A41" in result["matched_icd"]
