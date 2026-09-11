"""Регрессия на текст «Скопировать назначение».

``copyPrescription`` содержала все четыре дефекта, уже закрытых в других точках
вывода, — это ровно тот класс, что дал восемь находок за день: одна величина
извлекается независимо в каждом месте, где печатается.

1. ``computeDose(reg, w)`` без единицы препарата;
2. отсутствие проверки ``noDose`` — в буфер попало бы «0 мг» вместо отсутствующей
   дозы, что неотличимо от реальной нулевой;
3. сырая кратность ``reg.freq_per_day`` мимо ``formatFrequency``;
4. отсутствие ``mainReg`` — собственный режим главного компонента комбинации
   терялся, как терялся в ``calculate()``.

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

_HELPERS = (
    "formatUnits",
    "fmtDose",
    "doseUnitOf",
    "computeDose",
    "formatDuration",
    "freqTimesWord",
    "formatFrequency",
)

# Точная копия строк, которые copyPrescription кладёт в буфер обмена.
_SWEEP = """(() => {
  let checked = 0, zeroDose = 0, mgForUnits = 0, badFreq = 0, bareDur = 0, noDose = 0;
  const samples = [];
  for (const rec of DB.recommendations) for (const sc of (rec.scenarios || []))
    for (const ln of (sc.lines || [])) for (const d of (ln.drugs || [])) {
      const refs = d.combo_ref ? d.combo_ref : (d.drug_ref ? [d.drug_ref] : []);
      if (!refs.length) continue;
      const ref = DB.drugs_reference[refs[0]];
      if (!ref) continue;
      const unit = doseUnitOf(ref);
      for (const reg of (d.regimens || [])) {
        const mainReg = (reg.component_regimens && reg.component_regimens[refs[0]]) || reg;
        const r = computeDose(mainReg, 70, unit);
        if (r.noDose) { noDose++; continue; }
        checked++;
        const doseLine = 'Разовая доза: ' + fmtDose(r.singleMg, unit);
        const freqLine = 'Кратность: ' + formatFrequency(mainReg.freq_per_day, 'short');
        const durLine = 'Курс: ' + formatDuration(mainReg);
        if (r.singleMg === 0) zeroDose++;
        if (unit === 'ЕД' && /мг/.test(doseLine)) mgForUnits++;
        if (/раза в день/.test(freqLine)) badFreq++;
        if (/^\\s*Курс: \\d+(-\\d+)?\\s*$/.test(durLine)) bareDur++;
        if (unit === 'ЕД' && samples.length < 5) samples.push(doseLine + ' | ' + freqLine + ' | ' + durLine);
      }
    }
  return {
    checked: checked, noDose: noDose, zeroDose: zeroDose,
    mgForUnits: mgForUnits, badFreq: badFreq, bareDur: bareDur, samples: samples,
  };
})()"""


def _run(body: str, helpers: tuple[str, ...] = _HELPERS) -> dict:
    html = BUILT_HTML.read_text(encoding="utf-8")
    script = next(
        b
        for _a, b in re.findall(r"<script(?P<a>[^>]*)>(?P<b>.*?)</script>", html, re.S)
        if "function copyPrescription(" in b
    )
    db = json.loads(re.search(r'<script id="db-data" type="application/json">(.*?)</script>', html, re.S).group(1))

    parts = [f"const DB = {json.dumps(db, ensure_ascii=False)};\n"]
    parts.append(re.search(r"\nconst LATIN_FREQ = .*?;\n", script, re.S).group(0))
    for name in helpers:
        match = re.search(rf"\nfunction {re.escape(name)}\(.*?\n\}}\n", script, re.S)
        assert match, f"function {name}() not found in the built calculator script"
        parts.append(match.group(0))
    parts.append("\nconsole.log(JSON.stringify(")
    parts.append(body)
    parts.append("));\n")

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write("".join(parts))
        path = handle.name

    result = subprocess.run([node, path], capture_output=True, text=True, timeout=180, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_built_html_exists() -> None:
    assert BUILT_HTML.exists(), "run python db/build_html.py first"


def test_copied_text_has_no_silent_zero_and_no_unit_confusion() -> None:
    """Ни одной нулевой дозы, ни одного препарата в ЕД, напечатанного в «мг»."""
    verdict = _run(_SWEEP)

    assert verdict["checked"] >= 600, verdict
    assert verdict["zeroDose"] == 0, verdict
    assert verdict["mgForUnits"] == 0, verdict
    assert verdict["badFreq"] == 0, verdict
    assert verdict["bareDur"] == 0, verdict
    # Предусловие: режимы без числовой дозы существуют и отсекаются, а не печатаются.
    assert verdict["noDose"] >= 20, verdict
    assert verdict["samples"], "в БД не нашлось препаратов в ЕД — тест ничего не ловит"
    assert all("мг" not in s.split("|")[0] for s in verdict["samples"]), verdict["samples"]


def test_copy_refuses_a_regimen_without_a_numeric_dose() -> None:
    """Копия назначения — документ; «0 мг» вместо отсутствующей дозы недопустимо."""
    template = TEMPLATE.read_text(encoding="utf-8")
    body = template[template.index("function copyPrescription(") :]
    body = body[: body.index("\n}\n")]

    assert "noDose" in body, "copyPrescription не проверяет отсутствие дозы"
    assert "computeDose(mainReg, w, unit)" in body, "копия считает дозу без единицы препарата"
    # Отказ происходит ДО формирования текста, а не после.
    assert body.index("if(noDose)") < body.index("let txt ="), body


def test_copy_resolves_the_main_components_own_regimen() -> None:
    """Как и ``calculate()``: собственный режим главного компонента не теряется."""
    template = TEMPLATE.read_text(encoding="utf-8")
    body = template[template.index("function copyPrescription(") :]
    body = body[: body.index("\n}\n")]

    assert "reg.component_regimens[refs[0]]" in body, body
    assert "formatFrequency(mainReg.freq_per_day" in body, body
    assert "formatDuration(mainReg)" in body, body
    # Сырых полей мимо форматтеров не осталось.
    assert "reg.freq_per_day+' р/д'" not in body, body
    assert "formatDuration(reg)" not in body, body
