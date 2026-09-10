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
