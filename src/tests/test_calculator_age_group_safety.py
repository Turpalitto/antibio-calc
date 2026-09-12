"""Регрессия на подбор режима по возрастной группе в калькуляторе.

``getActiveRegimen()`` раньше откатывалась на ``regimens[0]``, когда для
выбранного возраста не находилось ни одного режима. Поскольку сценарий с
``age_group: "all"`` доступен во всех возрастах, это означало, что ребёнку или
новорождённому молча возвращался **взрослый** режим — и наоборот. Расчёт при
этом выглядел правдоподобно, то есть это тот самый класс «тихой неверной дозы»,
который репозиторий запрещает.

Тест исполняет **именно тот JavaScript, который попадает в собранный
``antibiotic_calc.html``**, на реальной БД из этого же файла.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILT_HTML = ROOT / "antibiotic_calc.html"
TEMPLATE = ROOT / "antibiotic_calc.html.template"

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="node is required to execute the shipped calculator script")

AGES = ("adult", "child", "neonate")


def _script_and_db() -> tuple[str, dict]:
    html = BUILT_HTML.read_text(encoding="utf-8")
    script = next(
        body
        for _attrs, body in re.findall(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S)
        if "function getActiveRegimen(" in body
    )
    db = json.loads(re.search(r'<script id="db-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    return script, db


def _get_active_regimen_source() -> str:
    script, _db = _script_and_db()
    match = re.search(r"\nfunction getActiveRegimen\(.*?\n\}\n", script, re.S)
    assert match, "function getActiveRegimen() not found in the built calculator script"
    return match.group(0)


def _run(body: str) -> dict:
    script, db = _script_and_db()
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(f"const DB = {json.dumps(db, ensure_ascii=False)};\n")
        handle.write(f"let activeDrug = null, activeAge = 'adult', activeRegimenIdx = 0;\n")
        handle.write(script_getter())
        handle.write("\nconsole.log(JSON.stringify(")
        handle.write(body)
        handle.write("));\n")
        path = handle.name

    result = subprocess.run([node, path], capture_output=True, text=True, timeout=300, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def script_getter() -> str:
    return _get_active_regimen_source()


def test_no_reachable_drug_returns_a_regimen_of_another_age_group() -> None:
    """Сплошной проход по всей БД: чужая возрастная группа недостижима."""
    verdict = _run(
        """(() => {
      const wrong = [];
      for (const r of DB.recommendations)
        for (const sc of (r.scenarios || [])) {
          const reachable = sc.age_group === 'all' ? ['adult','child','neonate'] : [sc.age_group];
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const age of reachable) {
                activeDrug = d; activeAge = age; activeRegimenIdx = 0;
                const got = getActiveRegimen();
                if (got && got.age_group !== age && got.age_group !== 'all') {
                  wrong.push(r.id + '/' + sc.id + '/' + (d.drug_ref || d.combo_ref) + '@' + age
                             + '->' + got.age_group);
                }
              }
        }
      return { wrong: wrong.slice(0, 10), count: wrong.length };
    })()"""
    )

    assert verdict["count"] == 0, f"regimens of another age group returned: {verdict['wrong']}"


def test_missing_regimen_yields_null_instead_of_a_substitute() -> None:
    """Реальные кейсы из БД: препарат есть, режима на возраст нет → null."""
    verdict = _run(
        """(() => {
      const cases = [
        ['anthrax','anthrax_cutaneous','amoxicillin'],
        ['typhoid_fever','typhoid_treatment','cefixime'],
        ['postop_prophylaxis','colorectal_surgery','metronidazole'],
      ];
      const out = {};
      for (const [did, sid, dref] of cases) {
        const dis = DB.recommendations.find(r => r.id === did);
        const sc = dis.scenarios.find(s => s.id === sid);
        const drug = sc.lines.flatMap(l => l.drugs).find(d => d.drug_ref === dref);
        const perAge = {};
        for (const age of ['adult','child','neonate']) {
          activeDrug = drug; activeAge = age; activeRegimenIdx = 0;
          const got = getActiveRegimen();
          perAge[age] = got ? got.age_group : null;
        }
        out[did + '/' + dref] = {
          regimenAges: drug.regimens.map(r => r.age_group),
          perAge,
        };
      }
      return out;
    })()"""
    )

    assert verdict, "no cases were exercised"
    for key, case in verdict.items():
        for age, got in case["perAge"].items():
            if got is not None:
                assert got in (age, "all"), f"{key}: возраст {age} получил режим {got}"
        # Хотя бы один возраст обязан остаться без расчёта — иначе кейс не тот.
        assert None in case["perAge"].values(), f"{key}: ожидался возраст без режима"


def test_a_matching_age_still_gets_its_regimen() -> None:
    """Фикс не должен ломать нормальный подбор."""
    verdict = _run(
        """(() => {
      let checked = 0, matched = 0;
      for (const r of DB.recommendations)
        for (const sc of (r.scenarios || [])) {
          const reachable = sc.age_group === 'all' ? ['adult','child','neonate'] : [sc.age_group];
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const age of reachable) {
                const has = (d.regimens || []).some(x => x.age_group === age || x.age_group === 'all');
                if (!has) continue;
                checked++;
                activeDrug = d; activeAge = age; activeRegimenIdx = 0;
                const got = getActiveRegimen();
                if (got && (got.age_group === age || got.age_group === 'all')) matched++;
              }
        }
      return { checked, matched };
    })()"""
    )

    # Порог — измеренное число пар «возраст × препарат с подходящим режимом»,
    # а не круглая цифра: он ловит случай, когда фикс начал отсекать лишнее.
    assert verdict["checked"] >= 400, verdict
    assert verdict["matched"] == verdict["checked"], verdict


def test_regimen_index_out_of_range_falls_back_within_the_same_age_group() -> None:
    """activeRegimenIdx не должен выводить за пределы своей возрастной группы."""
    verdict = _run(
        """(() => {
      let bad = 0;
      for (const r of DB.recommendations)
        for (const sc of (r.scenarios || []))
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const age of ['adult','child','neonate']) {
                activeDrug = d; activeAge = age; activeRegimenIdx = 99;
                const got = getActiveRegimen();
                if (got && got.age_group !== age && got.age_group !== 'all') bad++;
              }
      return { bad };
    })()"""
    )

    assert verdict["bad"] == 0


def test_template_has_no_silent_fallback_and_explains_itself() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "return (activeDrug.regimens || [])[0];" not in source
    assert "res-no-regimen" in source, "пользователю должна показываться причина отсутствия расчёта"
    assert "намеренно не подставляется" in source


def test_every_call_site_guards_the_null_regimen() -> None:
    """Все вызовы getActiveRegimen() обязаны проверять результат."""
    source = TEMPLATE.read_text(encoding="utf-8")

    occurrences = [m.start() for m in re.finditer(r"getActiveRegimen\(\)", source)]
    assert len(occurrences) >= 5, "ожидалось определение + минимум четыре вызова"

    for position in occurrences[1:]:
        following = source[position : position + 220]
        assert re.search(r"if\s*\(\s*!reg\s*\)", following), (
            "вызов getActiveRegimen() без проверки на null: " + following[:120]
        )


# ── сценарий чужой возрастной группы не должен давать расчёт ──────────────────

def _extract_fn(script: str, name: str) -> str:
    """Вытаскивает функцию по имени, считая вложенные фигурные скобки."""
    match = re.search(r"function " + re.escape(name) + r"\(", script)
    assert match, f"function {name}() not found in the built calculator script"
    i = match.start()
    depth = 0
    started = False
    while i < len(script):
        if script[i] == "{":
            depth += 1
            started = True
        elif script[i] == "}":
            depth -= 1
            if started and depth == 0:
                return script[match.start():i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces while extracting {name}()")


def _run_with(names, body: str) -> dict:
    """Исполняет собранный JS с произвольным набором функций."""
    script, db = _script_and_db()
    parts = [f"const DB = {json.dumps(db, ensure_ascii=False)};"]
    parts += [_extract_fn(script, n) for n in names]
    parts.append("let activeDrug=null, activeAge='adult', activeRegimenIdx=0, activeScenario=null;")
    parts.append("console.log(JSON.stringify(" + body + "));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(parts) + "\n")
        path = handle.name
    result = subprocess.run([node, path], capture_output=True, text=True, timeout=300, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_scenario_age_gate_blocks_exactly_the_mismatched_cases() -> None:
    """Ворота в ``calculate()``: сплошной проход по БД.

    Сценарий, адресованный другой возрастной группе, обязан блокировать расчёт.
    Предикат взят из shipped-кода дословно. В текущей БД 60 режимов лежат в
    сценарии чужой возрастной группы — все 60 должны блокироваться, и ни один
    подходящий по возрасту не должен.
    """
    verdict = _run_with(
        [],
        """(() => {
      // Опасен ровно один случай: режим лежит в сценарии чужой возрастной группы,
      // и пользователь выбирает возраст, равный age_group ЭТОГО режима. Тогда
      // подбор режима его вернёт (возраст совпал), и остановить могут только
      // ворота в calculate(). Несовпадение режима с возрастом само по себе
      // ловит подбор режима — это другая защита, смешивать их нельзя.
      let blocked = 0, leaked = 0;
      const sample = [];
      for (const r of DB.recommendations)
        for (const sc of (r.scenarios || []))
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const rg of (d.regimens || [])) {
                if (!rg.age_group || rg.age_group === 'all') continue;
                if (!sc.age_group || sc.age_group === 'all') continue;
                if (rg.age_group === sc.age_group) continue;
                const age = rg.age_group;
                const gate = sc.age_group !== 'all' && sc.age_group !== age;
                if (gate) {
                  blocked++;
                  if (sample.length < 3) sample.push(r.id + '/' + sc.id + '@' + age);
                } else {
                  leaked++;
                }
              }
      return { blocked: blocked, leaked: leaked, sample: sample };
    })()""",
    )
    assert verdict["leaked"] == 0 and verdict["blocked"] == 60, (
        "режим чужой возрастной группы прошёл бы ворота calculate(): "
        f"{verdict['leaked']} случаев, пример {verdict['sample']}"
    )


def test_calculate_refuses_before_computing_any_dose() -> None:
    """Отказ обязан идти ДО расчёта дозы, а не после сборки документа."""
    script, _db = _script_and_db()
    calc = _extract_fn(script, "calculate")

    gate = calc.index("activeScenario.age_group !== activeAge")
    dose = calc.index("computeDose(mainReg")
    assert gate < dose, (
        "проверка возрастной группы сценария стоит после computeDose — "
        "доза успеет рассчитаться до отказа"
    )
    # отказ сопровождается объяснением, а не молчаливым выходом
    assert "showNoCalculation(" in calc[:dose], (
        "при несовпадении возрастной группы calculate() обязан объяснять причину"
    )


def test_scenario_card_for_another_age_is_not_selectable() -> None:
    """Карточка чужого возраста видна, но не кликабельна."""
    script, _db = _script_and_db()
    render = _extract_fn(script, "renderScenarios")

    assert "if(ageMatch){" in render, (
        "renderScenarios обязан навешивать onclick только на подходящий по возрасту сценарий"
    )
    branch = render.index("if(ageMatch){")
    assert render.index("card.onclick = ()=>selectScenario") > branch, (
        "обработчик выбора должен быть внутри ветки ageMatch"
    )
    assert "card.onclick = null" in render[branch:], (
        "у карточки чужого возраста обработчик обязан сниматься явно"
    )


def test_browser_validator_reports_the_same_age_mismatches_as_the_build_validator() -> None:
    """Шапка браузера и сборочный валидатор обязаны видеть одно и то же.

    Раньше браузерный ``validateDB()`` находил 124 находки, а ``validate_db.js``
    на той же БД — 264; расхождение по возрастной группе (60) браузер не видел
    вовсе. Теперь обе стороны считают одно число.
    """
    script, db = _script_and_db()
    js = (
        f"const DB = {json.dumps(db, ensure_ascii=False)};\n"
        + _extract_fn(script, "validateDB")
        + "\nconst r = validateDB();\n"
        "console.log(JSON.stringify({errs: r.errs.length, warns: r.warns.length,"
        " age: r.warns.filter(w=>w.indexOf('вне сценария age_group')!==-1).length}));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(js)
        path = handle.name
    browser = json.loads(subprocess.run([node, path], capture_output=True, text=True,
                                        timeout=300, check=True).stdout.strip().splitlines()[-1])

    build = subprocess.run([node, str(ROOT / "db" / "validate_db.js")],
                           capture_output=True, text=True, timeout=300, check=True).stdout
    build_age = sum(1 for line in build.splitlines()
                    if "WARN:" in line and "outside scenario age_group" in line)

    assert browser["age"] == build_age == 60, (browser, build_age)


def test_no_path_reaches_a_mismatched_scenario() -> None:
    """Ни один путь выбора сценария не минует проверку возрастной группы.

    Снятие обработчика с карточки — только одна из трёх точек входа. Два других
    вызова ``selectScenario`` идут из автовыбора, и оба работают с переменными,
    которые устанавливаются исключительно при ``ageMatch``. Восстановление из
    URL сценарий не восстанавливает вовсе — только нозологию.
    """
    script, _db = _script_and_db()
    render = _extract_fn(script, "renderScenarios")
    restore = _extract_fn(script, "restoreFromHash")
    select_disease = _extract_fn(script, "selectDisease")

    # 1. Обработчик карточки — внутри ветки ageMatch, у чужой снят явно.
    assert render.index("card.onclick = ()=>selectScenario") > render.index("if(ageMatch){")
    assert "card.onclick = null" in render

    # 2. Автовыбор использует только совпавшие по возрасту переменные.
    assert "if(ageMatch && !firstVisible){ firstVisible = s; firstVisibleCard = card; }" in render
    assert "if(ageMatch && s === preferredScenario) preferredCard = card;" in render

    # 3. Восстановление из URL не выбирает сценарий.
    assert "selectScenario" not in restore, (
        "restoreFromHash не должен выбирать сценарий в обход проверки возраста"
    )
    assert "selectDisease(" in restore

    # 4. Нозология проходит через ворота источника до показа сценариев.
    assert select_disease.index("applyDiseaseSourceGate(d)") < select_disease.index("renderScenarios()")
