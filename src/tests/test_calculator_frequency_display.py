"""Регрессия на отображение кратности приёма в калькуляторе.

Раньше «раза в день» было записано в четырёх местах печатной формы, и все четыре давали
«8 раза в день» / «12 раза в день» — по-русски неверно (нужно «8 раз»), причём прямо в
рецепте. Замер: 49 режимов (кратности 8, 12 и 30).

Отдельно здесь закреплено, что латинской кратности в рецепте нет и быть не должно: в
регулируемой форме латынь живёт только в блоке ``Rp:``, а кратность и маршрут идут в
русскую строку ``D.S.``. Карты ``LATIN_FREQ`` и ``LATIN_ROUTE`` были удалены как
недостижимые — единственные вычислявшие их переменные никуда не подставлялись.

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


def _script_and_db() -> tuple[str, dict]:
    html = BUILT_HTML.read_text(encoding="utf-8")
    script = next(
        body
        for _attrs, body in re.findall(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S)
        if "function formatFrequency(" in body
    )
    db = json.loads(re.search(r'<script id="db-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    return script, db


def _extract(script: str, pattern: str, label: str) -> str:
    match = re.search(pattern, script, re.S)
    assert match, f"{label} not found in the built calculator script"
    return match.group(0)


def _run(body: str) -> dict:
    script, db = _script_and_db()
    harness = "".join(
        [
            _extract(script, r"\nfunction freqTimesWord\(.*?\n\}\n", "freqTimesWord()"),
            _extract(script, r"\nfunction formatFrequency\(.*?\n\}\n", "formatFrequency()"),
        ]
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(f"const DB = {json.dumps(db, ensure_ascii=False)};\n")
        handle.write(harness)
        handle.write("\nconsole.log(JSON.stringify(")
        handle.write(body)
        handle.write("));\n")
        path = handle.name

    result = subprocess.run([node, path], capture_output=True, text=True, timeout=180, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_built_html_exists() -> None:
    assert BUILT_HTML.exists(), "run python db/build_html.py first"


def test_pluralisation_matches_the_russian_rule_over_a_wide_range() -> None:
    """«раз» / «раза» сверяются с эталонным правилом на 1..200."""
    verdict = _run(
        r"""(() => {
          function reference(n){
            const m100 = n % 100, m10 = n % 10;
            if (m100 >= 11 && m100 <= 14) return 'раз';
            if (m10 === 1) return 'раз';
            if (m10 >= 2 && m10 <= 4) return 'раза';
            return 'раз';
          }
          const bad = [];
          for (let n = 1; n <= 200; n++) {
            if (freqTimesWord(n) !== reference(n)) bad.push(n + ': ' + freqTimesWord(n));
          }
          return { bad: bad };
        })()"""
    )

    assert verdict["bad"] == [], verdict


def test_every_frequency_in_the_db_renders_correctly() -> None:
    """Все кратности из БД (включая 8, 12, 30) печатаются без «8 раза»."""
    verdict = _run(
        r"""(() => {
          function reference(n){
            const m100 = n % 100, m10 = n % 10;
            if (m100 >= 11 && m100 <= 14) return 'раз';
            if (m10 === 1) return 'раз';
            if (m10 >= 2 && m10 <= 4) return 'раза';
            return 'раз';
          }
          const freqs = new Set();
          for (const rec of DB.recommendations) for (const sc of (rec.scenarios || []))
            for (const ln of (sc.lines || [])) for (const d of (ln.drugs || []))
              for (const reg of (d.regimens || [])) if (reg.freq_per_day != null) freqs.add(reg.freq_per_day);
          const wrong = [];
          const rendered = {};
          for (const f of freqs) {
            const full = formatFrequency(f);
            rendered[f] = full;
            if (/раза/.test(full) !== (reference(f) === 'раза')) wrong.push(f + ' -> ' + full);
          }
          return { freqs: [...freqs].sort((a, b) => a - b), wrong: wrong, rendered: rendered };
        })()"""
    )

    assert verdict["wrong"] == [], verdict
    # Предусловие: в БД действительно есть кратности вне LATIN_FREQ.
    assert set(verdict["freqs"]) >= {1, 2, 3, 4, 6, 8, 12, 30}, verdict
    assert verdict["rendered"]["8"] == "8 раз в день", verdict
    assert verdict["rendered"]["12"] == "12 раз в день", verdict
    assert verdict["rendered"]["30"] == "30 раз в день", verdict
    assert verdict["rendered"]["3"] == "3 раза в день", verdict


def test_latin_frequency_style_is_gone_and_not_silently_revived() -> None:
    """Латинской кратности в рецепте нет — и это намеренно.

    В регулируемой форме латынь живёт только в блоке ``Rp:`` (название препарата, форма,
    ``D.t.d.``), а кратность и маршрут идут в русскую строку ``D.S.``. Раньше в
    ``fillPrescriptionForm`` вычислялись ``freqStr`` (латинская кратность) и ``routeLat``
    (латинский маршрут), которые никуда не подставлялись: карты ``LATIN_FREQ`` и
    ``LATIN_ROUTE`` были недостижимы, а код выглядел так, будто рецепт печатает латинскую
    кратность. Мёртвый код, похожий на фичу, хуже отсутствия кода.
    """
    template = TEMPLATE.read_text(encoding="utf-8")
    script, _db = _script_and_db()

    # Ни карт, ни ветки стиля не осталось. Проверяем по коду, а не по тексту:
    # пояснительный комментарий вправе называть удалённые константы.
    assert "const LATIN_FREQ" not in script
    assert "const LATIN_ROUTE" not in script
    assert "LATIN_FREQ[" not in script
    assert "LATIN_ROUTE[" not in script
    assert "style === 'latin'" not in script
    assert "formatFrequency(reg.freq_per_day, 'latin')" not in template

    # Латинские названия препарата и формы при этом остались — они часть Rp:.
    assert "LATIN_INN" in script
    assert "LATIN_FORM" in script
    assert "D.t.d. N " in template

    # Кратность и маршрут в русской строке D.S. — на месте.
    assert "'внутрь'" in template and "'внутримышечно'" in template and "'внутривенно'" in template


def test_no_dead_local_variables_in_the_prescription_printer() -> None:
    """Ни одна локальная переменная печати не должна вычисляться впустую.

    Именно так проявился дефект: ``freqStr`` и ``routeLat`` считались и не читались.
    Проверка перебирает все объявления в ``fillPrescriptionForm`` и требует, чтобы каждое
    имя встречалось в теле больше одного раза.
    """
    script, _db = _script_and_db()
    match = re.search(r"\nfunction fillPrescriptionForm\(", script)
    assert match, "fillPrescriptionForm() not found in the built calculator script"
    i, depth, started = match.start(), 0, False
    while i < len(script):
        if script[i] == "{":
            depth += 1
            started = True
        elif script[i] == "}":
            depth -= 1
            if started and depth == 0:
                i += 1
                break
        i += 1
    body = script[match.start():i]

    declared = re.findall(r"^\s*(?:const|let)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", body, re.M)
    assert declared, "в fillPrescriptionForm должны быть локальные переменные"

    dead = [
        name
        for name in declared
        if len(re.findall(r"(?<![.\w])" + re.escape(name) + r"(?![\w])", body)) <= 1
    ]
    assert dead == [], f"переменные вычисляются и не используются: {dead}"


def test_absent_frequency_renders_as_a_dash_not_a_number() -> None:
    """Отсутствующая кратность — прочерк, а не «null раза в день»."""
    verdict = _run(
        r"""(() => ({
          nul: formatFrequency(null),
          undef: formatFrequency(undefined),
          zero: formatFrequency(0),
          neg: formatFrequency(-1),
          nan: formatFrequency(NaN),
          inf: formatFrequency(Infinity),
        }))()"""
    )

    assert set(verdict.values()) == {"—"}, verdict
    assert "null" not in json.dumps(verdict, ensure_ascii=False), verdict
    assert "NaN" not in json.dumps(verdict, ensure_ascii=False), verdict


def test_no_hardcoded_freq_phrase_remains_in_the_template() -> None:
    """«раза в день» больше не записано ни в одной точке вывода."""
    template = TEMPLATE.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in template.splitlines()
        if "раза в день" in line and not line.strip().startswith("//")
    ]

    assert offenders == [], offenders
    assert "function formatFrequency(" in template
    assert "LATIN_FREQ[reg.freq_per_day] ||" not in template
