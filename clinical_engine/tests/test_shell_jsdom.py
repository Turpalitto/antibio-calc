"""The built calculator shell, driven through the DOM in jsdom (2026-10-14).

``js/shell_smoke.js`` loads ``antibiotic_calc.html`` with the static Tailwind
build inlined, operates the page through real events (``input`` / ``change`` /
``click`` / ``keydown``) and runs axe-core in its main states. These tests pin
the wiring between the visible controls and what the physician sees:

* the age typed next to the unit selector drives the age group — the header
  card used to carry a second ``id="patient-age"`` that swallowed the input;
* pregnancy / GFR produce advisory flags and the MIS text carries them;
* a penicillin allergy marks the amoxicillin card; blocked and «БЕЗ КР»
  records show their banners and never a dose;
* history drawer and guideline modal are keyboard-closable dialogs with focus
  management; the page has one ``<main>``, one ``<h1>`` and no duplicate ids;
* axe-core reports **no** violations (colour contrast excluded — jsdom has no
  layout) in the main view, with the drawer open and with the modal open.

Requires ``node`` and the root devDependencies (``npm ci``: jsdom, axe-core);
skipped when they are absent, which is why CI installs them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HTML = PROJECT_ROOT / "antibiotic_calc.html"
CSS = PROJECT_ROOT / "vendor" / "app.css"
AXE = PROJECT_ROOT / "node_modules" / "axe-core" / "axe.min.js"
JSDOM = PROJECT_ROOT / "node_modules" / "jsdom" / "package.json"
HARNESS = Path(__file__).with_name("js") / "shell_smoke.js"


@pytest.fixture(scope="module")
def shell() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    if not (AXE.is_file() and JSDOM.is_file()):
        pytest.skip("root devDependencies missing — run `npm ci` (jsdom + axe-core)")
    completed = subprocess.run(
        [node, str(HARNESS), str(HTML), str(CSS), str(AXE)],
        capture_output=True, text=True, check=False, timeout=300, cwd=PROJECT_ROOT,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    result = json.loads(completed.stdout)
    assert "exception" not in result, result["exception"]
    assert result["consoleErrors"] == [], result["consoleErrors"]
    return result


def test_shell_boots_with_the_shipped_db_and_a_clean_document(shell: dict) -> None:
    assert shell["dbBlockingErrors"] == 0
    assert "120 нозологий" in shell["header"] and "65 расчётных" in shell["header"]
    assert shell["duplicateIds"] == [], "duplicate ids break getElementById-driven handlers"
    assert shell["landmarks"] == {"main": 1, "header": 1, "h1": 1}


def test_search_select_drug_weight_flow_through_the_dom(shell: dict) -> None:
    assert shell["search"]["resultsVisible"] is True and shell["search"]["results"] >= 1
    assert shell["search"]["statusVisible"] is True and shell["search"]["status"].startswith(f"Найдено: {shell['search']['results']} нозологии"), shell["search"]
    assert shell["disease"]["searchStatusVisible"] is False, "the count disappears with the result list once a nosology is chosen"
    assert shell["disease"]["status"] == "CR_REFERENCE_CALCULATION"
    assert shell["disease"]["activeCr"].startswith("КР МЗ РФ #")
    adult = shell["adult"]
    assert adult["ageGroup"] == "adult"
    assert adult["resultVisible"] is True
    assert adult["mg"] == "100 мг" and "1 таб" in adult["tabs"]
    assert adult["flagsVisible"] is False


def test_age_typed_next_to_the_unit_selector_drives_the_age_group(shell: dict) -> None:
    age7 = shell["age7"]
    assert age7["ageGroup"] == "child", "the visible age input must switch the group (duplicate-id regression)"
    assert age7["noticeVisible"] is True and "7 лет" in age7["notice"]
    # 70 kg on a children's mg/kg scheme is refused, visibly
    assert "ЗАБЛОКИРОВАН" in age7["doseBlock"]
    assert shell["age7months"]["ageGroup"] == "child" and "7 мес" in shell["age7months"]["notice"]
    assert shell["age19"]["ageGroup"] == "adult" and shell["age19"]["flagsVisible"] is False


def test_pregnancy_and_gfr_flags_reach_the_banner_and_the_mis_text(shell: dict) -> None:
    preg = shell["pregGfr"]
    assert preg["flagsVisible"] is True
    assert "Беременность" in preg["flags"] and "Доксициклин" in preg["flags"]
    mis = shell["mis"]["text"]
    assert mis.startswith("НАЗНАЧЕНИЕ АНТИБАКТЕРИАЛЬНОЙ ТЕРАПИИ")
    assert "возраст 19 лет" in mis and "беременность/лактация" in mis and "СКФ 25 мл/мин" in mis
    assert "Доксициклин" in mis and "ВНИМАНИЕ" in mis
    assert "КР #—" not in mis
    assert shell["afterReset"] == {"flagsVisible": False, "noticeVisible": False}


def test_implausible_gfr_is_flagged_on_screen_and_in_the_mis_text(shell: dict) -> None:
    """«1500» in the GFR field is a creatinine, not a GFR — the renal rules would
    see a healthy kidney and go silent; «0» is anuria and must run them."""
    high = shell["gfrHigh"]
    assert "СКФ 1500 мл/мин — неправдоподобно высокое значение (> 200)" in high["flags"] and "креатинин" in high["flags"]
    assert len(high["mis"]) >= 1 and high["mis"][-1].startswith("Предупреждение: СКФ 1500 мл/мин — неправдоподобно"), high["mis"]
    assert "СКФ" not in shell["gfrZero"]["flags"], "doxycycline needs no renal adjustment — GFR 0 adds nothing for it"
    zero = shell["newPatient"]["filled"]["gfrZeroFlags"]
    assert "СКФ 0 мл/мин: «Амоксициллин» — СКФ<30" in zero and "неправдоподобно" not in zero, zero


def test_penicillin_allergy_marks_the_amoxicillin_card(shell: dict) -> None:
    allergy = shell["allergy"]
    assert allergy["badgeVisible"] is True
    assert allergy["amoxCardClass"] and "border-red-300" in allergy["amoxCardClass"]
    assert "Противопоказано" in allergy["amoxText"]


def test_blocked_and_no_cr_records_show_their_banners(shell: dict) -> None:
    assert "ЗАБЛОКИРОВАН" in shell["blocked"]["banner"]
    assert shell["noCr"]["status"] == "NO_FEDERAL_CR_EXPERT_BASIS"
    assert "Нет федеральной КР" in shell["noCr"]["banner"]


def test_theme_toggle_persists(shell: dict) -> None:
    assert shell["theme"] == {"before": False, "after": True, "stored": "dark"}


def test_history_drawer_is_a_keyboard_closable_dialog(shell: dict) -> None:
    drawer = shell["drawer"]
    assert drawer == {"openClass": True, "inert": False, "ariaHidden": "false", "focusOnClose": "drawer-close"}
    assert shell["drawerAfterEscape"] == {"openClass": False, "inert": True}


def test_guideline_modal_is_a_labelled_dialog_with_focus_return(shell: dict) -> None:
    modal = shell["modal"]
    assert modal["visible"] is True
    assert modal["role"] == "dialog" and modal["labelledBy"] == "modal-cr-title"
    assert modal["title"].startswith("Урогенитальный хламидиоз")
    assert modal["focusTag"] == "BUTTON"
    assert shell["modalAfterEscape"] == {"visible": False, "focusId": "btn-guideline-modal"}


def test_course_units_agree_across_exports_and_course_is_in_days(shell: dict) -> None:
    c = shell["courseUnits"]
    # doxycycline 100 mg × 2/day × 7 days of 100 mg tablets → 14 tablets everywhere
    assert c["misTotal"] == c["rpDtd"] == c["rxDtd"] == "14", c
    assert "по 100 мг" in c["rpSigna"] and "Принимать внутрь" in c["rpSigna"] and "курс 7 дней" in c["rpSigna"], c
    assert c["misCourse"] == "Курс лечения: 7 дней" and c["rxCourse"].startswith("Курс: 7 дней"), c
    assert c["screenCourse"] == "7 дней" and "1 таб 100 мг" in c["perDose"], c


def test_default_form_is_the_strength_that_fits_the_single_dose(shell: dict) -> None:
    f = shell["defaultForm"]
    assert f["drug"] == "amoxicillin" and f["dose"] == "500 мг"
    assert f["active"] == ["500 мг"], f  # not the DB-first «125 мг» (= «4 таб 125 мг»)
    assert f["perDose"] == "(1 таб 500 мг)"
    a = f["amoxiclav"]
    assert a["drug"] == "amoxiclav" and a["dose"] == "875 мг"
    assert a["active"] and a["active"][0].startswith("875+125 мг"), a
    assert a["perDose"] == "(1 таб 875+125 мг)", "combination strength: one tablet named by the product, not «7 таб 125 мг»"


def test_changing_the_allergy_status_keeps_the_selected_drug_form_and_regimen(shell: dict) -> None:
    """renderLines() with no preference fell back to the FIRST card: marking a
    penicillin allergy after choosing a non-first drug switched the calculation to
    the first drug (amoxicillin — the one just declared contraindicated) and reset
    the form chip. The place must survive the re-render in both directions."""
    keep = shell["allergy"]["keepSelection"]
    assert keep["before"] == keep["afterSevere"] == keep["afterNone"], keep
    assert keep["before"].startswith("cefuroxime|") and keep["before"].split("|")[3] == "1", "non-first drug, non-default form chip"
    assert keep["activeCard"].startswith("Цефуроксим") and any(f.startswith("Амоксициллин") for f in keep["flaggedCards"]), keep


def test_age_group_change_keeps_the_scenario_and_drug_when_the_scenario_fits(shell: dict) -> None:
    """Typing an age (or clicking a group chip) re-rendered the scenarios from
    scratch — first eligible scenario, first drug. For an «all»-age scenario the
    physician's drug now stays: without a regimen for the new group it shows the
    explicit age block (ciprofloxacin at 7 y) instead of silently becoming
    ceftriaxone; with one it re-derives the regimen (1250 mg at 25 kg ↔ 2000 mg)."""
    k = shell["ageKeepsSelection"]
    assert k["adult"] == "salmonellosis_severe|2|ciprofloxacin|po|adult" and k["adultBlock"] == ""
    assert k["child"] == "salmonellosis_severe|2|ciprofloxacin|po|child" and k["childResultHidden"] is True
    assert k["childBlock"].startswith("РАСЧЁТ ЗАБЛОКИРОВАН: для препарата «Ципрофлоксацин» в БД нет ни одной схемы дозирования для возрастной группы «дети»")
    assert k["childCeftriaxone"] == "salmonellosis_severe|1|ceftriaxone|iv|child|1250"
    assert k["backToAdult"] == "salmonellosis_severe|1|ceftriaxone|iv|adult|2000" and k["backBlock"] == ""
    assert k["adultOnlyScenarioAtChildAge"].startswith("cap_adult_out_no_risk|1|amoxicillin|po|child|РАСЧЁТ ЗАБЛОКИРОВАН"), "an adult-only scenario still falls back to the first one, fail-visible"
    assert k["inferredChild"] == "aom_child_standard|1|amoxicillin|po|child|ok,ok"
    assert k["inferredAdult"].startswith("aom_child_standard|1|amoxicillin|po|adult|dim,dim|РАСЧЁТ ЗАБЛОКИРОВАН"), "a weight-inferred group change dims the child-only scenarios and blocks, fail-visible"


def test_default_form_chip_follows_the_weight_until_the_physician_picks_one(shell: dict) -> None:
    """The default suspension strength is chosen from the single dose; a weight typed
    after the drug used to leave the chip on «125 мг/5 мл» (45 ml per dose) where the
    same child typed first opened on «250 мг/5 мл» (22.5 ml). An explicit chip
    survives weight changes; the next drug card starts from the default again."""
    k = shell["formFollowsWeight"]
    assert k["noWeight"] == "4|125 мг/5 мл|—"
    assert k["weightAfterDrug"] == "5|250 мг/5 мл|22.5"
    assert k["weightAfterDrug"] == k["weightBeforeDrug"], "the entry order must not change the default form"
    assert k["pickedStays"] == "4|125 мг/5 мл|14.4|true"
    assert k["nextDrugPicked"] is False


def test_copy_falls_back_to_execcommand_without_navigator_clipboard(shell: dict) -> None:
    """navigator.clipboard exists only in secure contexts; a shell served over plain
    http from an intranet host used to throw a TypeError on «Копировать для МИС»
    and show nothing. The legacy copy is used and the outcome is always toasted."""
    c = shell["clipboardFallback"]
    assert c["toast"] == "✅ Назначение скопировано для МИС"
    assert c["startsWith"].startswith("НАЗНАЧЕНИЕ") and c["copiedLines"] >= 10
    assert c["leftover"] == 0, "the helper textarea must not stay in the DOM"
    assert c["failToast"].startswith("Ошибка копирования — буфер обмена недоступен")


def test_denied_storage_access_does_not_break_init_deep_link_or_theme(shell: dict) -> None:
    """When the browser blocks site data, touching localStorage throws SecurityError.
    setupTheme() used to throw inside init(), so the history store, the service
    worker and the #hash deep link never initialised and the theme toggle threw
    on every click."""
    s = shell["storageDenied"]
    assert s["errors"] == [], s["errors"]
    assert s["dbLoaded"] is True and s["hashDisease"] == "cap_adult"
    assert s["toggleTheme"] == "dark"
    assert s["historyOpens"] is True


def test_ctrl_p_prints_the_current_state_never_a_stale_prescription(shell: dict) -> None:
    """The print stylesheet shows #prescription-form alone, but only the «Печать»
    button filled it: Ctrl+P / the browser menu printed whatever the form held —
    the previous patient's prescription, or nothing. beforeprint now refills it
    from the current state, and an empty / blocked state prints the reason."""
    p = shell["ctrlP"]
    assert p["filled"]["drugs"].startswith("Amoxicillini 500 mg") and p["filled"]["patient"] == "Петров П.П."
    assert p["afterReset"] == {"drugs": "", "signa": "", "patient": "—", "trust": p["afterReset"]["trust"]}
    assert p["afterReset"]["trust"].startswith("ПЕЧАТЬ НЕВОЗМОЖНА: расчёт не выполнен")
    assert p["blocked"]["drugs"] == "" and p["blocked"]["signa"] == "" and p["blocked"]["patient"] == "—"
    assert p["blocked"]["trust"].startswith("ПЕЧАТЬ ЗАБЛОКИРОВАНА. РАСЧЁТ ЗАБЛОКИРОВАН: Вес 0.5 кг")


def test_blocked_calculation_is_not_saved_to_history(shell: dict) -> None:
    """saveToHistory() checked only the age regimen: a 300-kg (or 25 kg for a
    10-day-old) calculation was saved with its doses while the block text
    promised «не может быть сохранён». Found by the random-walk fuzz."""
    h = shell["historyBlocked"]
    assert h["added"] == 0 and h["toast"] == "Сохранение заблокировано: расчёт не выполнен", h
    assert h["block"].startswith("РАСЧЁТ ЗАБЛОКИРОВАН: Вес 300 кг")
    assert h["addedWhenValid"] == 1


def test_history_open_restores_the_saved_calculation_and_hashchange_navigates(shell: dict) -> None:
    h = shell["historyRestore"]
    assert h["button"] and h["button"].startswith("Открыть расчёт / Амоксициллин + Клавулановая кислота, Внебольничная пневмония у взрослых"), h
    assert h["elsewhere"] == "cap_child|child"
    assert h["after"] == h["before"], h  # nosology, scenario, line, drug, route, form chip, regimen
    assert h["doseAfter"] == h["doseBefore"] and h["doseAfter"].startswith("875 мг"), h
    assert h["age"].endswith("|adult|70"), "patient context (age group, weight) restored with the entry"
    assert h["drawerOpen"] is False and h["toast"] == "Расчёт из истории открыт"
    # GFR / pregnancy / allergy are part of the saved context: the re-opened calculation
    # shows the same renal flag it was saved with, not the next patient's inputs
    assert h["context"] == "25|no|cephalosporin", h["context"]
    assert "СКФ 25 мл/мин" in h["flagsBefore"] and h["flagsAfter"] == h["flagsBefore"], (h["flagsBefore"], h["flagsAfter"])
    assert h["allergyBadge"] is True
    # the name is part of the entry too: the printed form of a re-opened calculation must
    # not carry the NEXT patient's name with this patient's age / weight / regimen
    assert h["patientName"] == "Иванов И.И. / Иванов И.И.", h["patientName"]
    hc = shell["hashchange"]
    assert hc["before"] != "cap_adult" and hc["after"] == "cap_adult" and hc["scenario"] == "cap_adult_out_no_risk", hc
    # the L<n> part opens that line (first drug); a scenario outside the current age group
    # waits with a note until the patient data moves into its group, then opens with its line
    assert hc["line"] == "adult|salmonellosis_severe|2|ciprofloxacin", hc
    assert hc["pendingState"] == "child|||", hc
    assert hc["pendingNote"].startswith("Сценарий из ссылки «Амбулаторно, коморбидный пациент") and "рассчитан на группу «взрослые»" in hc["pendingNote"]
    assert hc["resolvedState"] == "adult|cap_adult_out_comorbid|1|amoxiclav" and hc["resolvedNote"] is False, hc
    assert hc["otherDiseaseClearsNote"] is True


def test_printed_form_header_names_patient_age_and_weight_as_text(shell: dict) -> None:
    h = shell["rxHeader"]
    assert "Пациент: Иванова А.<img src=x onerror=alert(1)>" in h["text"], h
    assert h["html"] is False, "Ф.И.О. must never be parsed as markup"
    assert "Возраст: 19 лет (взрослые)" in h["text"], h
    assert "Вес: 70 кг" in h["text"], h


def test_search_matches_tokens_endings_icd_and_drug_names(shell: dict) -> None:
    r = shell["searchRecall"]
    assert r["пневмония дети"]["n"] == 1 and r["пневмония дети"]["first"].startswith("Внебольничная пневмония у детей")
    assert r["h. pylori"]["n"] == 1 and "pylori" in r["h. pylori"]["first"].lower()
    assert r["амоксициллин"]["n"] >= 20, "drug-name search must list the nosologies using the drug"
    assert r["амоксициллин"]["blockedBeforeComputable"] is False, "computable records must come first"
    assert r["J18"]["n"] >= 2 and "пневмония" in r["J18"]["first"].lower()
    # ICD-10 is hierarchical: the full code a physician types («J18.9», pneumonia
    # unspecified) finds the records listed under the category «J18» — it used to find
    # only the one record that spells «J18.9» out; a lone letter covers nothing
    assert r["J18.9"]["n"] == r["J18"]["n"] and r["J18.9"]["names"] == r["J18"]["names"], (r["J18.9"], r["J18"])
    assert r["j18.9 дети"]["n"] == 1 and r["j18.9 дети"]["first"].startswith("Внебольничная пневмония у детей"), r["j18.9 дети"]
    # a space after the letter («J 18», «j 18.9») is still the code, not «j» + «18» (10 hits)
    assert r["J 18"]["names"] == r["J18"]["names"] and r["j 18.9"]["names"] == r["J18.9"]["names"], (r["J 18"], r["j 18.9"])
    # T90: a Cyrillic look-alike letter in front of the digits is the Latin one — «Н66» is
    # H66 (otitis), «В20» is B20 (HIV), «О85» is O85 (postpartum endometritis); the keyboard
    # map used to make them nothing / D20 (a tumour) / J85 (a lung abscess)
    for cyr, lat in (("Н66", "H66"), ("В20", "B20"), ("О85", "O85")):
        assert r[cyr]["n"] >= 1 and r[cyr]["names"] == r[lat]["names"], (cyr, r[cyr], r[lat])
    assert r["В20"]["n"] == 1 and r["В20"]["names"][0].startswith("ВИЧ-инфекция у взрослых"), r["В20"]
    assert r["О85"]["n"] == 1 and r["О85"]["names"][0].startswith("Послеродовой эндометрит"), r["О85"]
    assert r["К81"]["n"] == 1 and r["К81"]["names"][0].startswith("Острый холецистит и холангит"), r["К81"]
    # a sibling subcode is not covered: «J18.0» finds the two «J18» records, not the
    # nosocomial record that spells «J18.9»
    assert r["J18.0"]["n"] == 2 and all(n.startswith("Внебольничная пневмония") for n in r["J18.0"]["names"]), r["J18.0"]
    assert r["J1"]["n"] >= r["J18"]["n"], r["J1"]
    assert r["J"]["n"] == 0, r["J"]
    assert r["N39.0"]["n"] >= 2 and all("N39" in n or "ИМП" in n or "цистит" in n.lower() or "пиелонефрит" in n.lower() or "мочев" in n.lower() for n in r["N39.0"]["names"]), r["N39.0"]
    assert r["отит взрослые"]["n"] == 1 and "у взрослых" in r["отит взрослые"]["first"]
    assert r["xyzzy"]["n"] == 0
    # one typo per word, only for tokens that match nothing exactly; ranked after exact hits
    assert r["пневмания дети"]["n"] == 1 and r["пневмания дети"]["first"].startswith("Внебольничная пневмония у детей")
    # T88: a list made of one-typo guesses says so — in the status and on every row
    assert r["пневмания дети"]["status"] == "Найдено: 1 нозология — точного совпадения нет, показаны похожие названия; проверьте написание «пневмания дети».", r["пневмания дети"]
    assert all("• похожее название, не точное совпадение" in row for row in r["пневмания дети"]["rows"]), r["пневмания дети"]
    assert r["пневмания дети"]["first"].startswith("Внебольничная пневмония у детей")
    # … while stem / word-start hits are plain matches («тонзилит» → «тонзиллит», «отит»)
    for q in ("тонзилит", "отит", "цистит", "J18", "амоксициллин"):
        assert "похожие" not in r[q]["status"] and not any("похожее название" in row for row in r[q]["rows"]), (q, r[q])
    assert r["тонзилит"]["names"][:2] == ["Острый тонзиллит / фарингит (БГСА) у взрослых", "Острый тонзиллит / фарингит (БГСА) у детей"], r["тонзилит"]
    assert r["амоксицилин"]["n"] == r["амоксициллин"]["n"]
    # a word-start hit outranks a hit inside another word; an exact token is never widened
    assert r["цистит"]["names"][0] == "Острый неосложнённый цистит у женщин" and r["цистит"]["names"][-1] == "Острый холецистит и холангит", r["цистит"]
    assert "цистицеркоз" not in " ".join(r["цистит"]["names"]).lower()
    assert r["бронхит"]["names"] == ["Бронхит"], "«бронхит» has an exact hit, so бронхиолит must not be pulled in"
    # T87: a stem shorter than 4 letters counts only at a word start — «отит» no longer pulls
    # «некрОТИзирующий» / «антибиОТИкопрофилактика» (8 hits), «рожа» no longer «новоРОЖдённых» (7)
    assert r["отит"]["names"] == ["Острый средний отит у детей", "Острый средний отит у взрослых"], r["отит"]
    assert r["рожа"]["names"] == ["Рожа у взрослых"], r["рожа"]
    # T91: a stem shorter than 6 letters counts only at a word start, and two letters are
    # dropped only from a 6+ token — «ангина» no longer finds «холАНГИт», «ковид»
    # «муКОВИсцидоз», «грипп» («гри») the mushroom-poisoning record, «колит» («кол»)
    # «КОЛенного» / «КОЛьца» / «сКОЛиоз», «асцит» («асци») «фАСЦИит»; a long stem still
    # matches inside a word («тонзиллита» → «паратонзиллит»)
    assert [n.split("МКБ")[0] for n in r["ангина"]["names"]] == ["Острый тонзиллит / фарингит (БГСА) у взрослых", "Острый тонзиллит / фарингит (БГСА) у детей"], r["ангина"]
    assert r["грипп"]["n"] == 0 and r["ковид"]["n"] == 0, (r["грипп"], r["ковид"])
    assert r["колит"]["names"] == ["Clostridioides difficile-ассоциированная инфекция (псевдомембранозный колит)", "Язвенный колит", "Некротизирующий энтероколит (НЭК)"], r["колит"]
    assert r["асцит"]["names"] == ["Спонтанный бактериальный перитонит (СБП)"], r["асцит"]
    assert r["тонзиллита"]["names"] == ["Острый тонзиллит / фарингит (БГСА) у взрослых", "Острый тонзиллит / фарингит (БГСА) у детей", "Перитонзиллярный абсцесс (паратонзиллит)"], r["тонзиллита"]
    # T92: the word a short stem starts may go on for an ending or a suffix only (≤ 5
    # letters) — «таза» no longer finds every piperacillin/ТАЗобактам record (13 → 2),
    # «холера» no longer «ХОЛЕцистит», «гепатит» no longer «ГЕПАТобластома»; derivations
    # stay («язва» → «язвенная болезнь» / «Язвенный колит», «рана» → «раневой инфекции»)
    assert r["таза"]["names"] == ["Воспалительные заболевания органов таза (ВЗОТ)", "Повреждения тазового кольца"], r["таза"]
    assert r["холера"]["n"] == 0, r["холера"]
    assert r["гепатит"]["names"] == ["Хронический вирусный гепатит B"], r["гепатит"]
    assert {"Helicobacter pylori-инфекция (язвенная болезнь)", "Язвенный колит", "Сибирская язва"} <= set(r["язва"]["names"]), r["язва"]
    assert "Укусы животных (профилактика и лечение раневой инфекции)" in r["рана"]["names"], r["рана"]


def test_search_status_counts_hits_and_says_when_nothing_matched(shell: dict) -> None:
    """A silent empty list was the only sign that nothing matched; 110 hits for
    «ин» had no count. The status line is role=status/aria-live for screen readers."""
    r = shell["searchRecall"]
    assert r["xyzzy"]["n"] == 0 and r["xyzzy"]["boxVisible"] is False and r["xyzzy"]["statusVisible"] is True
    assert r["xyzzy"]["status"] == "Ничего не найдено по запросу «xyzzy». Попробуйте код МКБ-10 (например, J18), другое название или синоним."
    assert r["ин"]["n"] > 20 and r["ин"]["status"].startswith(f"Найдено: {r['ин']['n']} нозологий (с закрытым расчётом: ") and r["ин"]["status"].endswith(") — уточните запрос.")
    assert r["х"] == {"n": 0, "status": "", "statusVisible": False, "boxVisible": False, "first": None, "names": [], "rows": [], "blockedBeforeComputable": False}, "a single letter is not a query yet — and the previous list is cleared, not just hidden"
    assert r["J18"]["status"].startswith(f"Найдено: {r['J18']['n']} ") and "уточните" not in r["J18"]["status"]


def test_search_treats_yo_and_ye_as_the_same_letter(shell: dict) -> None:
    """Russian keyboards skip «ё»: «лёгк» found 1 nosology and «легк» 3 (different
    sets), «трёх» found nothing while «трех» found 4. Both sides are folded now."""
    r = shell["searchRecall"]
    # (T87 trimmed the 3-letter stems «лег» / «тре» to word starts: «фЛЕГмона» and
    # «аортоЛЕГочной» are no longer hits, so the sets are smaller — and still identical)
    assert r["лёгк"]["names"] == ["Абсцесс лёгкого / эмпиема плевры"] and r["лёгк"]["names"] == r["легк"]["names"], (r["лёгк"], r["легк"])
    assert r["трёх"]["names"] == ["Трехпредсердное сердце"] and r["трёх"]["names"] == r["трех"]["names"], (r["трёх"], r["трех"])
    assert r["НОВОРОЖДЁННЫЕ"]["n"] >= 1, r["НОВОРОЖДЁННЫЕ"]


def test_cards_are_keyboard_activatable_and_deep_link_restores_scenario(shell: dict) -> None:
    kb = shell["keyboard"]
    assert kb["hitRole"] == "button" and kb["hitTabindex"] == "0"
    assert kb["diseaseAfterEnter"] == "chlamydia_urogenital"
    assert kb["scenarioRoles"] and all(r == "button/0" for r in kb["scenarioRoles"])
    assert kb["scenarioAfterSpace"] and kb["scenarioCardActive"] is True
    assert kb["drugRole"] == "button" and kb["drugAfterEnter"] and kb["resultVisible"] is True
    assert kb["hash"].startswith("#chlamydia_urogenital/" + kb["scenarioAfterSpace"] + "/L")
    assert kb["restoredScenario"] == kb["scenarioAfterSpace"]


def test_allergy_status_travels_with_every_export(shell: dict) -> None:
    """Regression: severe penicillin allergy + amoxicillin showed ⛔ on screen,
    but the MIS text, the Latin recipe, the printed form and the history entry
    left without a word about it."""
    al = shell["allergy"]
    assert al["bannerVisible"] is True and "противопоказан" in al["bannerTitle"].lower()
    needle = "ВНИМАНИЕ: Аллергия («Пенициллины (анафилаксия / отёк)»): препарат ПРОТИВОПОКАЗАН по аллергоанамнезу"
    assert needle in al["mis"]
    assert "! " + needle in al["rp"] and al["rp"].startswith("Rp.: Amoxicillini")
    assert al["rxSafety"]["hidden"] is False and needle in al["rxSafety"]["text"]
    assert "⚠ Аллергия («Пенициллины (анафилаксия / отёк)»)" in al["history"]
    # no allergy → the printed safety block disappears again
    assert al["rxSafetyAfterReset"]["hidden"] is True and al["rxSafetyAfterReset"]["text"] == ""


def test_pregnancy_flag_reaches_the_printed_form(shell: dict) -> None:
    """Doxycycline needs no renal adjustment, so GFR 25 adds nothing here — the
    pregnancy contraindication alone must appear on the paper."""
    rx = shell["rxPregGfr"]
    assert rx["safetyHidden"] is False
    assert rx["safety"].startswith("ВНИМАНИЕ: Беременность/лактация: «Доксициклин» — Противопоказан")


def test_combination_partner_dose_is_exported_not_only_shown(shell: dict) -> None:
    """Listeriosis = ampicillin + gentamicin: the screen computed gentamicin
    350 mg × 1 (5 mg/kg × 70 kg) but the MIS text and the printed form named
    ampicillin only (the partner survived as free text in «Указания»)."""
    cb = shell["combo"]
    assert cb["drug"] == '["ampicillin","gentamicin"]'
    assert "Гентамицин" in cb["screen"] and "350 мг" in cb["screen"]
    assert "Компонент комбинации: Гентамицин — по 350 мг 1 р/д" in cb["mis"]
    assert "Gentamicini" in cb["rx"] and "Гентамицин — по 350 мг 1 р/д" in cb["rx"]
    assert "Компоненты комбинации (одновременно)" in cb["rx"]
    # T83: the copied Latin Rp named ampicillin only — the partner now follows the Signa
    rp_lines = cb["rp"].split("\n")
    assert rp_lines[0].startswith("Rp.: Ampicillini") and rp_lines[2].startswith("S.: "), cb["rp"]
    assert "Одновременно (компоненты комбинации, отдельные Rp.):" in rp_lines, cb["rp"]
    partner = [ln for ln in rp_lines if ln.startswith("Gentamicini (Гентамицин) ")]
    assert partner and "— по 350 мг 1 р/д" in partner[0] and "(сут. 350 мг)" in partner[0], cb["rp"]
    # T85: the history entry / drawer row name the whole combination and word the course
    # as the exports do («21 день», not the raw DB «21»)
    he = cb["historyEntry"]
    assert he["drug"] == "Ампициллин + Гентамицин" and he["course"] == "21 день" and he["duration"] == "21", he
    assert he["singleMg"] == 2000 and he["freq"] == 6, he
    row = cb["historyRow"]
    assert "Ампициллин + Гентамицин" in row and "2000 мг × 6 р/д, курс 21 день" in row, row


def test_switching_to_a_blocked_nosology_drops_the_previous_regimen(shell: dict) -> None:
    """Regression: after doxycycline/chlamydia, selecting a source-gate-blocked
    record left activeDrug in place, so the header print button produced a
    prescription with the old regimen under the new, blocked diagnosis."""
    st = shell["stale"]
    assert st["drugBefore"] == "doxycycline" and st["gate"] == "blocked"
    assert st["drugAfter"] is None and st["scenarioAfter"] is None
    assert st["hash"] == "#" + st["blockedId"]
    assert st["staleCards"] == 0
    assert st["printed"] == 0 and st["rxDrugs"] == ""
    assert st["toast"] == "Выберите препарат"


def test_route_form_mismatch_falls_back_visibly(shell: dict) -> None:
    """A scenario route with no matching form must not silently widen the
    offer: the shell shows every form AND an amber notice (validate_db.js
    warns about the same gap at build time)."""
    rm = shell["routeMismatch"]
    assert rm["noteHiddenBefore"] is True
    assert rm["noteVisible"] is True and rm["noteHiddenAfter"] is True
    assert "в/в" in rm["noteText"] and "показаны все доступные формы" in rm["noteText"]
    assert rm["tabs"] == ["per os"]


def test_service_worker_update_banner_is_opt_in_reload(shell: dict) -> None:
    banner = shell["updateBanner"]
    assert banner["hiddenBefore"] is True and banner["visibleAfter"] is True
    assert "новая версия" in banner["text"].lower() and "Перезагрузить" in banner["text"]
    assert banner["role"] == "status"


@pytest.mark.parametrize("state", ["main", "drawer_open", "modal_open", "source_gated", "computed_with_banners"])
def test_axe_core_reports_no_violations(shell: dict, state: str) -> None:
    report = shell["axe"][state]
    assert report["passes"] > 20, "axe did not actually run"
    assert report["violations"] == [], json.dumps(report["violations"], ensure_ascii=False, indent=1)


def test_saved_dark_theme_is_applied_before_the_stylesheet_loads() -> None:
    """setupTheme() runs from init() at the end of <body>, i.e. after the light
    page has painted — a head script must apply the stored theme first."""
    html = HTML.read_text(encoding="utf-8")
    head = html.split("</head>", 1)[0]
    script_at = head.find("localStorage.getItem('antibio_theme')==='dark'")
    css_at = head.find('<link href="./vendor/app.css"')
    assert 0 < script_at < css_at, "pre-paint theme script must precede the stylesheet link"
    assert "documentElement.classList.add('dark')" in head[script_at:script_at + 200]


def test_children_open_on_the_suspension_with_a_measurable_dose_volume(shell: dict) -> None:
    """A 25-kg child on amoxicillin 90 mg/kg/day (1125 mg per dose) used to open
    on the DB-first «125 мг/5 мл» = 45 ml per dose; now the concentration whose
    volume is closest to measurable wins, and the MIS text names the daily dose
    and carries the large-volume warning when the physician picks a weak one."""
    ld = shell["liquidDefault"]
    assert ld["child25"]["active"] == ["250 мг/5 мл"] and ld["child25"]["dose"] == "1125 мг", ld["child25"]
    assert ld["child25"]["ml"] == "22.5 мл"
    assert "Суточная доза: 2250 мг" in ld["child25"]["mis"]
    assert "Предупреждение: разовый объём 22.5 мл велик" in ld["child25"]["mis"]
    # the printed form now dispenses bottles like the Rp text (it had no D.t.d. for a suspension)
    assert "D.t.d. N. 5 in pulv. pro susp." in ld["child25"]["rp"]
    assert ld["child25"]["rxDtd"] == ["D.t.d. N 5 in pulv. pro susp. (фл. по 100 мл; на курс 450.0 мл, 10 дн.)"], ld["child25"]["rxDtd"]
    # 7-kg infant, 315 mg per dose: 125 mg/5 ml would be 12.6 ml, 250 mg/5 ml is 6.3 ml
    assert ld["infant7"]["active"] == ["250 мг/5 мл"] and ld["infant7"]["ml"] == "6.3 мл", ld["infant7"]
    assert ld["lowPicked"]["active"] == ["125 мг/5 мл"] and ld["lowPicked"]["ml"] == "45.0"
    assert "разовый объём 45.0 мл велик" in ld["lowPicked"]["mis"]
    # an older child whose best suspension is still > 15 ml opens on tablets that divide evenly
    assert ld["teen40"]["active"] == ["500 мг"] and ld["teen40"]["dose"] == "1500 мг", ld["teen40"]
    assert ld["teen40"]["tabs"] == "(3 таб 500 мг)"


def test_weight_impossible_for_the_age_and_implausible_age_block_every_output(shell: dict) -> None:
    """Typed values are checked against each other: 25 kg at 10 days (a typo for
    2.5 → a 10× mg/kg dose) and 150 years both block the screen, the MIS copy
    and the printed form; the notice is shown while typing, drug or no drug."""
    pl = shell["plausibility"]
    neo = pl["neonate25"]
    assert neo["hidden"] is False and neo["blocking"] == "true"
    assert neo["text"].startswith("Вес 25 кг при возрасте 10 дн. — неправдоподобное сочетание для новорождённого (> 7 кг)"), neo
    assert neo["block"].startswith("РАСЧЁТ ЗАБЛОКИРОВАН: Вес 25 кг при возрасте 10 дн.")
    assert neo["mis"] == "" and "заблокировано" in neo["toast"], neo
    # a real neonate weight with an explicit age: no notice at all (the old «<40 кг при
    # группе новорождённые» hint only applies when no age was entered)
    assert pl["neonate32"]["hidden"] is True, pl["neonate32"]
    assert pl["age150"]["po"] is False and pl["age150"]["block"].startswith("РАСЧЁТ ЗАБЛОКИРОВАН: Возраст 150 лет — неправдоподобное значение (> 120 лет)"), pl["age150"]
    assert pl["age150"]["notice"].startswith("Возраст 150 лет — неправдоподобное значение")
    assert pl["age35"]["notice"] == "Возраст 35 лет → группа «взрослые»."
    assert pl["w300"]["hidden"] is False and pl["w300"]["blocking"] == "true" and "> 250 кг" in pl["w300"]["text"]


def test_search_is_operable_from_the_keyboard(shell: dict) -> None:
    """Enter opens the top-ranked result, ArrowDown/ArrowUp walk the list and
    return to the input, Escape clears the query without touching the calculation."""
    ks = shell["keyboardSearch"]
    assert ks["n"] >= 2 and ks["first"] == "Острый тонзиллит / фарингит (БГСА) у взрослых", ks
    assert ks["focusAfterDown"] is True and ks["focusAfterDown2"] is True and ks["backToInput"] is True, ks
    assert ks["clearedValue"] == "" and ks["boxHiddenAfterEscape"] is True
    assert ks["openedDisease"] == "Острый тонзиллит / фарингит (БГСА) у взрослых"


def test_drops_form_is_grouped_with_the_topical_route_not_per_os(shell: dict) -> None:
    """``drops`` is a validator-accepted form type; the shell's route grouping
    fell through to per os for it (an ear-drop form would have been offered as
    an oral dose). Now it joins the topical group like a cream."""
    df = shell["dropsForm"]
    assert df["before"] == ["per os"]
    assert df["tabs"] == ["per os", "местно"], df
    assert df["topicalForms"] == ["0.3 % капли ушныетест"] and df["poHasDrops"] is False


def test_new_patient_clears_the_whole_context_and_the_stale_allergy_banner(shell: dict) -> None:
    """One action for the next patient: weight, age, GFR, pregnancy, allergy, the
    age group and the calculation are all reset — the previous patient's GFR or
    pregnancy must not silently colour the next prescription. The nosology «✕»
    used to leave the «противопоказан» allergy banner on screen with no drug."""
    npat = shell["newPatient"]
    assert npat["filled"]["po"] is True and npat["filled"]["allergyBanner"] is True and npat["filled"]["group"] == "adult"
    assert npat["filled"]["allergyBannerAfterDiseaseReset"] is False and npat["filled"]["allergyBannerAgain"] is True
    assert (npat["weight"], npat["age"], npat["unit"], npat["gfr"], npat["pregnancy"], npat["allergy"]) == ("", "", "years", "", "unknown", "none")
    assert npat["group"] == "child" and npat["activeChip"] == ["child"] and npat["userPickedAge"] is False and npat["patientAgeDays"] is None
    assert npat["resultHidden"] is True and npat["emptyState"] is True and npat["disease"] is None and npat["search"] == ""
    assert npat["allergyBanner"] is False and npat["weightWarnHidden"] is True
    # the Ф.И.О. goes with the patient (it used to stay and be printed on the next
    # prescription); the physician field is session-level and stays
    assert npat["name"] == "" and npat["doctor"] == "Д-р Иванова"
    assert npat["toast"] == "Данные пациента и расчёт сброшены"


def test_default_route_follows_the_db_order_and_a_picked_route_follows_the_physician(shell: dict) -> None:
    """Route tabs were rendered in the fixed po/im/iv order of the groups object, so
    ceftriaxone «iv, im» for inpatient CAP opened on в/м and azithromycin «iv,
    per_os» for severe CAP on per os. Now the tabs (and the default) follow the
    order the scenario record lists; a route the physician clicked follows them
    across the drug cards (a drug without it opens on its own default and the
    preference survives) and a new scenario starts from the DB default again."""
    r = shell["routeFollows"]
    assert r["ceftriaxoneDefault"] == "cap_adult_in_mild|ceftriaxone|iv|null|в/в,в/м"
    assert r["imPicked"] == "cap_adult_in_mild|ceftriaxone|im|im"
    assert r["amoxiclavIvOnly"] == "cap_adult_in_mild|amoxiclav|iv|im|в/в"
    assert r["ceftriaxoneAgain"] == "cap_adult_in_mild|ceftriaxone|im|im", "the picked route survives a drug that lacks it"
    assert r["afterAllergy"] == "cap_adult_in_mild|ceftriaxone|im|im", "a context re-render keeps the picked route"
    assert r["newScenario"] == "cap_adult_in_severe|ceftriaxone|iv|null|в/в"
    assert r["azithromycinSevere"] == "cap_adult_in_severe|azithromycin|iv|null|в/в,per os"


def test_a_denied_history_replace_state_does_not_abort_a_selection(shell: dict) -> None:
    """history.replaceState throws SecurityError in sandboxed documents (srcdoc /
    sandboxed iframes, some file:// viewers, blob: URLs). updateHash() was the
    last statement of selectDisease / selectScenario / selectDrug and the only
    statement inside the personal-candidate try block after the render — the
    throw surfaced as a console error or a false «BLOCKED» status. The deep link
    is a convenience: the selection and the reset must complete without it."""
    r = shell["replaceStateDenied"]
    assert r["state"] == "pyelonephritis_adult|apn_mild|true", r
    assert r["resultVisible"] is True and r["drugCards"] > 1, r
    assert r["afterReset"] == "null|null|null|empty", r
    assert r["consoleErrors"] == 0, "a denied replaceState must stay silent"


def test_tab_stays_inside_an_open_dialog_and_the_backdrop_closes_the_modal(shell: dict) -> None:
    """The guideline modal (aria-modal) and the history drawer had Escape and a
    focus return but no focus trap: Tab wandered into the page behind the dimmed
    backdrop (WCAG 2.4.3; ARIA APG modal dialog), and only the × button closed
    the modal. Tab now cycles inside the open dialog, a focus that escaped is
    pulled back, and a click on the backdrop (not on the panel) closes the modal."""
    t = shell["dialogFocus"]
    assert t["modalOpen"] is True and t["modalItems"] >= 2 and t["initialFocusIsClose"] is True, t
    assert t["wrapForward"] is True and t["wrapBackward"] is True and t["pulledBack"] is True, t
    assert t["panelClickKeepsOpen"] is True and t["backdropClickCloses"] is True and t["focusBackOnOpener"] is True, t
    assert t["drawerItems"] >= 3 and t["drawerInitialFocus"] is True, t
    assert t["drawerWrapBackward"] is True and t["drawerWrapForward"] is True and t["drawerClosedByEscape"] is True, t


def test_the_source_gate_of_a_blocked_record_holds_for_every_re_render(shell: dict) -> None:
    """REAL HAZARD found by the fuzz gate: a record under the source gate
    (`calculation_blocked` — «расчёт закрыт» until the owner verifies the source)
    opened with no scenario cards, but the next typed age / age chip / weight-
    inferred group / allergy change re-rendered the scenarios of the gated record,
    selected its first drug and computed, exported, printed and saved a dose under
    the red block notice. renderScenarios() is now the choke point and
    calculationBlockReason() names the gate for MIS / Rp / print / history."""
    g = shell["sourceGate"]
    gated = "null|null|0|0|true|false|false"
    assert g["opened"] == gated, g
    assert g["afterAge"] == gated and g["afterChip"] == gated and g["afterAllergy"] == gated, g
    assert g["afterHash"] == gated, "a #hash deep link into a gated record must not open its scenario"
    assert g["historyAdded"] == 0 and g["misCopied"] is False and g["misToast"] == "Нет активного расчёта", g
    assert g["printDrugs"] == "" and g["printTrust"].startswith("ПЕЧАТЬ НЕВОЗМОЖНА"), g
    assert g["blockReason"].startswith("РАСЧЁТ ЗАБЛОКИРОВАН"), g
    assert g["recovered"] == "aom_child|true|false", g


def test_the_allergy_banner_leaves_with_the_drug_when_no_scenario_fits_the_group(shell: dict) -> None:
    """Found by the fuzz notice invariants: selectDrug() refreshes the allergy
    banner, resetDisease() hides it (T45), but a record with NO scenario for the
    current age group (cap_adult at 7 y, via the list or a #hash) selects no drug
    and left the previous drug's «Препарат противопоказан по аллергоанамнезу!»
    banner on screen. renderScenarios() now refreshes it in every outcome."""
    b = shell["allergyBannerFollowsDrug"]
    assert b["withAmoxicillin"] == "Внимание: Препарат противопоказан по аллергоанамнезу!", b
    assert b["noScenarioForGroup"] == "null|0|false", b
    assert b["backWithAmoxicillin"] is True, b
    assert b["viaHash"] == "pyelonephritis_adult|null|false", b


def test_history_saved_after_a_reload_with_the_tab_store_is_visible(shell: dict) -> None:
    """readHistoryEntries() read the tab store whenever it existed while
    writes went there only with the consent box on: after a reload (box off by
    default, stored entries present) «Сохранить в историю» toasted success but the
    drawer kept showing the stored list without the new entry. The consent given
    earlier in the tab now comes back with its entries (box checked), and reads
    follow the same rule as writes."""
    h = shell["historyReload"]
    assert h["afterReload"] == "true|1|1", h
    assert h["afterSave"] == "2|2|Сохранено в историю (вкладка)", h
    assert h["afterOptOut"] == "2|0|true", h
    assert h["afterSaveMemoryOnly"] == "3|0", h


def test_history_restore_of_a_record_closed_by_the_source_gate_stays_closed(shell: dict) -> None:
    """An entry saved before a later DB build closed its record («расчёт закрыт»):
    «Открыть расчёт» opens the nosology under the block notice only, and the next
    age input / chip keeps it closed; MIS refuses. Before T66 the stale result
    stayed on screen after the restore and the next age input rebuilt the scenarios,
    computed and printed «Amoxicillini 500 mg …» under the red notice."""
    g = shell["historyGatedRestore"]
    assert g["saved"] == "amoxicillin|true", g
    closed = "cap_adult|null|null|0|false|РАСЧЁТ ЗАБЛОКИРОВАН: источник отозван"
    assert g["restored"] == "false|Открыта нозология; сценарий из истории недоступен|" + closed, g
    assert g["afterAge"] == closed, g
    assert g["misToast"] == "Нет активного расчёта" and g["printed"] == "", g


def test_history_restore_brings_back_the_group_chosen_over_a_typed_age(shell: dict) -> None:
    """An entry saved at 150 months (12 y) with the «взрослые» chip chosen over the typed
    age (the explicit-age notice flags the mismatch) must re-open as it was saved:
    the restore used to re-apply the age only, the group fell back to «дети» and the
    adult scenario was not re-opened («препарат … недоступен для этой возрастной
    группы», no dose)."""
    o = shell["historyRestoreGroupOverride"]
    assert o["saved"] == "adult|cap_adult_out_comorbid|moxifloxacin|150|months|true|true", o
    assert o["entry"] == "adult|150|months", o
    assert o["restored"] == "true|Расчёт из истории открыт|adult|cap_adult_out_comorbid|moxifloxacin|150|months|true|true", o
    caution = "Возраст 12 лет соответствует группе «дети», расчёт выполнен для группы «взрослые» (выбрана вручную)."
    assert o["misCaution"] == "Предупреждение: " + caution, o
    assert o["printedCaution"] == "Предупреждение: " + caution, o


def test_printed_date_uses_the_russian_format_for_a_picked_date(shell: dict) -> None:
    """The date field becomes type=date on focus, so a picked date is ISO
    «2026-10-15»; the printed form said «Дата: 2026-10-15» next to a default of
    «15.10.2026». Both print as DD.MM.YYYY; «Новый пациент» keeps the date."""
    pd = shell["printDate"]
    assert pd["picked"] == "15.10.2026", pd
    assert pd["keptAfterNewPatient"] == "2026-10-15", pd
    assert pd["today"] == pd["todayExpected"], pd


def test_regimen_chips_follow_the_age_group(shell: dict) -> None:
    """Amoxicillin for AOM has three child regimens and none for neonates: the
    «новорождённые» chip shows the age block alone — the three child chips used to
    stay under it, clickable and dead (a click only moved activeRegimenIdx). Back on
    «дети» the chips return (first regimen selected again)."""
    r = shell["regimenChipsFollowGroup"]
    assert r["child"] == "true|3|1|3|true|", r
    assert r["neonate"].startswith("false|0|0|0|false|РАСЧЁТ ЗАБЛОКИРОВАН: для препарата «Амоксициллин»"), r
    assert r["childAgain"] == "true|3|0|3|true|", r



def test_an_mg_per_kg_regimen_without_a_weight_leaves_by_no_door(shell: dict) -> None:
    """T77: ceftriaxone 50 mg/kg/day for a 7-year-old with no weight: the screen is a
    pending state («—», the amber «нужен вес» notice, not a block), but the chart text
    used to go out as «Схема приёма: 50-75 мг/кг/сут 1 р/сут», the Rp with «N. ___»
    and a mg/kg Signa, the form printed and the history saved with no dose. Now all
    four refuse and name the gap; with 25 kg typed they work again."""
    n = shell["noWeightExport"]
    reason = "введите вес пациента — доза этого режима рассчитывается по мг/кг и без веса не определена"
    assert n["state"] == 'ut_child_in|ceftriaxone||""|true|—|Для этого режима нужен вес пациента — доза рассчитывается по мг/кг.', n
    assert n["mis"] == "|Копирование заблокировано: " + reason, n
    assert n["rp"] == "|Копирование рецепта заблокировано: " + reason, n
    assert n["save"] == "0|Сохранение заблокировано: " + reason, n
    assert n["print"] == "||ПЕЧАТЬ НЕВОЗМОЖНА: введите вес пациента — доза этого режима ", n
    assert n["misWithWeight"].startswith("Схема приёма: по 1250 мг в/в 1 р/сут|"), n
    assert n["printWithWeight"] == "По 1250 мг внутривенно, 1 раз в день, медленно за 5 мин", n


def test_quick_nosology_tags_follow_the_patient_group(shell: dict) -> None:
    """T84: every quick tag code (H66, J18, J03, J01, N30, N10) has an adult AND a child
    record; the tag used to open the first record in DB order (children's otitis for an
    adult, adults' pneumonia / pyelonephritis for a child) and then showed the «нет схемы
    для группы» block. Now the record for the patient's group opens; two equally fitting
    records (adult + N30: cystitis vs prophylaxis) or no fitting record (neonate) go to the
    search list for the physician to pick."""
    qt = shell["quickTags"]
    assert qt["tags"] == ["H66", "J18", "J03", "J01", "N30", "N10"]
    for key, rec in (
        ("adultH66", "otitis_media_adult"), ("childH66", "aom_child"),
        ("adultJ18", "cap_adult"), ("childJ18", "cap_child"),
        ("adultN10", "pyelonephritis_adult"), ("childN10", "ut_child"),
    ):
        assert qt[key]["picked"] == rec, (key, qt[key])
        assert qt[key]["list"] == [] and qt[key]["search"] == "" and qt[key]["header"], (key, qt[key])
    for key, names in (
        ("adultN30", ["Профилактика рецидивирующих ИМ", "Острый неосложнённый цистит у "]),
        ("neonateH66", ["Острый средний отит у детейH66", "Острый средний отит у взрослых"]),
    ):
        assert qt[key]["picked"] is None and qt[key]["header"] == "", (key, qt[key])
        assert qt[key]["list"] == names and qt[key]["status"] == "Найдено: 2 нозологии.", (key, qt[key])
        assert qt[key]["search"] == key[-3:], qt[key]


def test_search_ranks_the_patient_group_first_once_it_is_set(shell: dict) -> None:
    """T86: «пневмония» in a fresh tab lists the records in DB order (adults first); after
    the physician types a child's age the children's record leads and the other rows say
    «нет схемы для группы «дети»»; the adult chip re-ranks the list that is already on
    screen; «Новый пациент» returns to DB order."""
    gs = shell["groupSearch"]
    assert gs["fresh"][:2] == ["Внебольничная пневмония у взрослых", "Внебольничная пневмония у детей"], gs["fresh"]
    assert gs["childTyped"][:2] == ["Внебольничная пневмония у детей", "Внебольничная пневмония у взрослых"], gs["childTyped"]
    assert "нет схемы для группы" not in gs["childRows"][0], gs["childRows"][0]
    assert all("• нет схемы для группы «дети»" in row for row in gs["childRows"][1:]), gs["childRows"]
    assert gs["adultChip"][:3] == ["Внебольничная пневмония у взрослых", "Нозокомиальная (внутрибольничная) пневмония", "Аспирационная пневмония"], gs["adultChip"]
    assert gs["adultChip"].index("Внебольничная пневмония у детей") == 3, gs["adultChip"]
    assert "• нет схемы для группы «взрослые»" in gs["adultRows"][3] and "нет схемы" not in gs["adultRows"][0], gs["adultRows"]
    assert gs["adultOtitis"][:2] == ["Острый средний отит у взрослых", "Острый средний отит у детей"], gs["adultOtitis"]
    assert gs["freshOtitis"][:2] == ["Острый средний отит у детей", "Острый средний отит у взрослых"], gs["freshOtitis"]
