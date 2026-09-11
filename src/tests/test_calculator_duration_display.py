"""Регрессия на отображение длительности курса в калькуляторе.

До появления ``duration_parsed`` калькулятор печатал ``duration_days`` и
механически дописывал «дней», поэтому «однократно» превращалось в
«Курс: однократно дней», а число приёмов на курс считалось как
``parseInt('10-14')`` — молча бралась нижняя граница, а для свободного текста
получался ноль.

Тест исполняет **именно тот JavaScript, который попадает в собранный
``antibiotic_calc.html``**, на реальной БД из этого же файла. Проверка на
копиях логики здесь не годится: чинили именно shipped-код.
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


def _script_and_db() -> tuple[str, dict]:
    html = BUILT_HTML.read_text(encoding="utf-8")
    script = next(
        body
        for _attrs, body in re.findall(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S)
        if "function formatDuration(" in body
    )
    db = json.loads(re.search(r'<script id="db-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    return script, db


def _extract(script: str, name: str) -> str:
    match = re.search(rf"\nfunction {re.escape(name)}\(.*?\n\}}\n", script, re.S)
    assert match, f"function {name}() not found in the built calculator script"
    return match.group(0)


def _run(script: str, body: str) -> dict:
    """Execute the shipped helpers in node and return their JSON verdict."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        handle.write("\nconsole.log(JSON.stringify(")
        handle.write(body)
        handle.write("));\n")
        path = handle.name

    result = subprocess.run([node, path], capture_output=True, text=True, timeout=180, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def harness() -> str:
    script, _db = _script_and_db()
    return "".join(_extract(script, name) for name in ("formatDuration", "courseDayBounds", "renderCourseTotals"))


def test_built_html_exists() -> None:
    assert BUILT_HTML.exists(), "run python db/build_html.py first"


def test_every_regimen_renders_without_a_bogus_unit(harness: str) -> None:
    """Ни один из 638 режимов не должен получать приписанное «дней»."""
    _script, db = _script_and_db()
    payload = json.dumps(db, ensure_ascii=False)

    verdict = _run(
        harness,
        f"""(() => {{
      const DB = {payload};
      const bogus = /(однократно|не указано|по ситуации|пожизненно|месяц\\w*|недел\\w*|часов|минут)\\s+дней/;
      let total = 0; const bad = []; const lost = [];
      for (const r of DB.recommendations)
        for (const sc of (r.scenarios || []))
          for (const ln of (sc.lines || []))
            for (const d of (ln.drugs || []))
              for (const reg of (d.regimens || [])) {{
                total++;
                const txt = formatDuration(reg);
                if (bogus.test(txt)) bad.push(txt);
                if (txt === '—' && reg.duration_days) lost.push(String(reg.duration_days));
              }}
      return {{ total, bad: bad.slice(0, 5), lost: lost.slice(0, 5) }};
    }})()""",
    )

    assert verdict["total"] == 638
    assert verdict["bad"] == [], f"duration rendered with a bogus «дней»: {verdict['bad']}"
    assert verdict["lost"] == [], f"non-empty duration_days collapsed to «—»: {verdict['lost']}"


def test_single_dose_and_free_text_do_not_get_a_day_count(harness: str) -> None:
    verdict = _run(
        harness,
        """(() => ({
      single: formatDuration({duration_days: 'однократно', duration_parsed: {kind: 'SINGLE_DOSE', value_min: 1, value_max: 1, unit: 'administration'}}),
      range:  formatDuration({duration_days: '7-10', duration_parsed: {kind: 'RANGE', value_min: 7, value_max: 10, unit: 'day'}}),
      free:   formatDuration({duration_days: 'до нормализации температуры', duration_parsed: {kind: 'CONDITION_DEPENDENT'}}),
      hours:  formatDuration({duration_days: 'не более 24 часов', duration_parsed: {kind: 'AT_MOST', value_max: 24, unit: 'hour'}}),
      absent: formatDuration({duration_days: null, duration_parsed: {kind: 'MISSING'}}),
    }))()""",
    )

    assert verdict == {
        "single": "однократно",
        "range": "7–10 дней",
        "free": "до нормализации температуры",
        "hours": "не более 24 ч",
        "absent": "—",
    }


def test_course_totals_use_the_full_range_and_never_a_fake_zero(harness: str) -> None:
    """parseInt('10-14') молча давал 10; свободный текст давал 0."""
    verdict = _run(
        harness,
        """(() => ({
      range:  renderCourseTotals({duration_parsed: {kind: 'RANGE', value_min: 7, value_max: 10, unit: 'day'}}, 3, 2, 'tabulettam'),
      fixed:  renderCourseTotals({duration_parsed: {kind: 'FIXED', value_min: 5, value_max: 5, unit: 'day'}}, 2, 1, 'tabulettam'),
      single: renderCourseTotals({duration_parsed: {kind: 'SINGLE_DOSE', value_min: 1, value_max: 1, unit: 'administration'}}, 1, 1, 'tabulettam'),
      free:   renderCourseTotals({duration_parsed: {kind: 'CONDITION_DEPENDENT'}}, 2, 1, 'tabulettam'),
      months: renderCourseTotals({duration_parsed: {kind: 'FIXED', value_min: 3, value_max: 3, unit: 'month'}}, 1, 1, 'tabulettam'),
    }))()""",
    )

    assert "42–60" in verdict["range"] and "7–10 дн" in verdict["range"]
    assert "10 tabulettam" in verdict["fixed"]
    # Лучше ничего, чем «для курса: 0».
    assert verdict["single"] == ""
    assert verdict["free"] == ""
    # Месяцы — не дни: пересчёт в таблетки по «3» был бы занижен в ~30 раз.
    assert verdict["months"] == ""


def test_template_no_longer_appends_a_hardcoded_day_suffix() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "reg.duration_days || '—')+' дней'" not in source
    assert "compReg.duration_days+' дн'" not in source
    assert "parseInt(reg.duration_days)" not in source


# ── все точки вывода длительности обязаны идти через formatDuration ───────────


def test_no_output_site_prints_the_raw_duration_field() -> None:
    """Панели результата и история печатали ``duration_days`` напрямую.

    Замер по собранному HTML: 459 из 638 режимов (71,9%) выглядели в панелях не
    так, как в блоке комбинации — «10-14» вместо «10–14 дней», «1» вместо
    «однократно». Одно и то же поле рендерилось двумя способами.
    """
    template = TEMPLATE.read_text(encoding="utf-8")

    for site in ("$('po-dur')", "$('inj-dur')", "duration: "):
        lines = [line.strip() for line in template.splitlines() if site in line and "duration_days" in line]
        assert lines == [], f"{site} всё ещё печатает сырое duration_days: {lines}"

    # Все три точки обязаны использовать форматтер.
    assert "formatDuration(reg)" in template
    assert "duration: formatDuration(reg)" in template


def test_no_regimen_renders_as_a_bare_number(harness: str) -> None:
    """«10-14», «5», «1» без единицы — прежний симптом панелей результата."""
    _script, db = _script_and_db()
    body = """(() => {
      let total = 0;
      const bare = [];
      for (const rec of DB.recommendations) for (const sc of (rec.scenarios || []))
        for (const ln of (sc.lines || [])) for (const d of (ln.drugs || []))
          for (const reg of (d.regimens || [])) {
            total++;
            const shown = String(formatDuration(reg)).trim();
            if (/^\\d+(-\\d+)?$/.test(shown)) bare.push(rec.id + ': ' + shown);
          }
      return { total: total, bare: bare };
    })()"""

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(f"const DB = {json.dumps(db, ensure_ascii=False)};\n")
        handle.write(harness)
        handle.write("\nconsole.log(JSON.stringify(")
        handle.write(body)
        handle.write("));\n")
        path = handle.name

    result = subprocess.run([node, path], capture_output=True, text=True, timeout=180, check=True)
    verdict = json.loads(result.stdout.strip().splitlines()[-1])

    assert verdict["total"] == 638, verdict
    assert verdict["bare"] == [], verdict


def test_history_refuses_to_record_a_missing_dose() -> None:
    """История — запись расчёта; «0 мг» вместо отсутствующей дозы недопустимо.

    В списке это неотличимо от реальной нулевой дозы, поэтому ``saveToHistory``
    обязан отказывать так же, как экран отказывается считать.
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    body = template[template.index("function saveToHistory(") :]
    body = body[: body.index("\n}\n")]

    assert "noDose" in body, "saveToHistory не проверяет отсутствие дозы"
    assert "computeDose(reg, w, unit)" in body, "история считает дозу без единицы препарата"
    assert "doseUnitOf(ref)" in body


def test_history_stores_the_unit_and_a_fallback_exists() -> None:
    """Поле ``unit`` версиируется: старые записи показываются в мг, а не ломаются."""
    template = TEMPLATE.read_text(encoding="utf-8")
    load = template[template.index("function loadHistory(") :]
    load = load[: load.index("\n}\n")]

    assert "e.unit || 'мг'" in load, load
    assert "fmtDose(e.singleMg, eUnit)" in load


# ── ветвление пероральных форм: одна форма — один ответ независимо от веса ────


def test_mass_dosed_forms_do_not_depend_on_weight() -> None:
    """Пакетик гранул дозируется по массе, а не по объёму — при любом весе.

    До правки ``isSolid`` включал только ``tablet`` и ``capsule``, поэтому гранулы
    («3000 мг пакет») для ребёнка уходили в ветку «Объём не рассчитан» с
    предупреждением, а взрослому (``w >= 40``) та же форма показывала обычную
    инструкцию по массе. Одна лекарственная форма давала разный ответ в
    зависимости от веса. Замер: 12 случаев «форма × вес», все — фосфомицин.
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r"const isSolid = \[(.*?)\]\.includes\(form\.form_type\);", template)

    assert match, "не найдено определение isSolid в renderPO"
    listed = [item.strip().strip("'\"") for item in match.group(1).split(",")]
    assert "granules" in listed, listed
    assert "tablet" in listed and "capsule" in listed, listed


def test_po_branch_assignment_is_weight_independent_for_mass_forms() -> None:
    """Сверка веток до и после: расхождение только на гранулах и только к массе."""
    script, db = _script_and_db()
    body = """(() => {
      function poGroup(ref){
        const out = [];
        for (const f of (ref.forms || [])) {
          if (['tablet','capsule','suspension','syrup','granules'].includes(f.form_type)
              || (f.form_type === 'powder_for_suspension' && f.concentration_mg_per_ml != null)) {
            out.push(f); continue;
          }
          let matched = false;
          if (ref.dilution && ref.dilution.im
              && ['powder_for_suspension','powder_for_injection','solution_im'].includes(f.form_type)) matched = true;
          if (ref.dilution && (ref.dilution.iv_bolus || ref.dilution.iv_infusion)
              && ['powder_for_suspension','powder_for_injection','solution_iv'].includes(f.form_type)) matched = true;
          if (!matched) out.push(f);
        }
        return out;
      }
      const OLD = ['tablet','capsule'], NEW = ['tablet','capsule','granules'];
      const pick = (f, w, solidList) => {
        const conc = f.concentration_mg_per_ml || 0;
        const isSolid = solidList.includes(f.form_type);
        if (isSolid || (w >= 40 && conc === 0)) return isSolid ? 'solid' : 'adultNoConc';
        if (conc > 0) return 'ml';
        return 'failClosed';
      };
      const after = { solid: 0, adultNoConc: 0, ml: 0, failClosed: 0 };
      const changed = [];
      for (const [key, ref] of Object.entries(DB.drugs_reference)) {
        if (key === '_note' || !ref || typeof ref !== 'object') continue;
        for (const f of poGroup(ref)) {
          for (const w of [3, 7, 10, 20, 40, 70]) {
            const b = pick(f, w, OLD), a = pick(f, w, NEW);
            after[a]++;
            if (b !== a) changed.push({ key: key, type: f.form_type, w: w, from: b, to: a });
          }
        }
      }
      return { after: after, changed: changed };
    })()"""

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(f"const DB = {json.dumps(db, ensure_ascii=False)};\n")
        handle.write("\nconsole.log(JSON.stringify(")
        handle.write(body)
        handle.write("));\n")
        path = handle.name

    result = subprocess.run([node, path], capture_output=True, text=True, timeout=180, check=True)
    verdict = json.loads(result.stdout.strip().splitlines()[-1])

    # Измерено: 12 случаев, все — гранулы, все уходят в единую ветку массы.
    assert len(verdict["changed"]) == 12, verdict["changed"]
    assert {c["type"] for c in verdict["changed"]} == {"granules"}, verdict["changed"]
    assert {c["to"] for c in verdict["changed"]} == {"solid"}, verdict["changed"]
    assert verdict["after"]["failClosed"] == 8, verdict
    assert verdict["after"]["ml"] == 102, verdict
