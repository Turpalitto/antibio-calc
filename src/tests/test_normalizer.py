from normalizer import normalize_antibiotic


def test_normalize_amoxicillin():
    normalized, atc = normalize_antibiotic("амоксициллин")
    assert normalized == "amoxicillin"
    assert atc == "J01CA04"


def test_normalize_amoxiclav():
    normalized, atc = normalize_antibiotic("амоксициллин/клавуланат")
    assert normalized == "amoxicillin_clavulanate"
    assert atc == "J01CR02"


def test_normalize_ceftriaxone():
    normalized, atc = normalize_antibiotic("цефтриаксон")
    assert normalized == "ceftriaxone"
    assert atc == "J01DD04"


def test_normalize_case_insensitive():
    normalized, atc = normalize_antibiotic("Амоксициллин")
    assert normalized == "amoxicillin"
    assert atc == "J01CA04"


def test_normalize_unknown_drug():
    normalized, atc = normalize_antibiotic("неизвестный препарат")
    assert normalized == "неизвестный препарат"
    assert atc is None


def test_normalize_empty():
    normalized, atc = normalize_antibiotic("")
    assert normalized == ""
    assert atc is None
