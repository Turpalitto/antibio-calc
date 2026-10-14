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


@pytest.mark.parametrize("state", ["main", "drawer_open", "modal_open"])
def test_axe_core_reports_no_violations(shell: dict, state: str) -> None:
    report = shell["axe"][state]
    assert report["passes"] > 20, "axe did not actually run"
    assert report["violations"] == [], json.dumps(report["violations"], ensure_ascii=False, indent=1)
