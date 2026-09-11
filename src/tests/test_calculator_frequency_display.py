"""Регрессия на отображение кратности приёма в калькуляторе.

``LATIN_FREQ`` покрывает только {1, 2, 3, 4, 6}, а в БД есть кратности 8, 12 и 30.
Они падали в фолбэк ``reg.freq_per_day + ' раза в день'``, записанный в четырёх
местах печатной формы, и все четыре давали «8 раза в день» / «12 раза в день» —
по-русски неверно (нужно «8 раз»), причём прямо в рецепте. Замер: 49 режимов.

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
            _extract(script, r"\nconst LATIN_FREQ = .*?;\n", "LATIN_FREQ"),
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


def test_latin_style_keeps_curated_terms_and_degrades_gracefully() -> None:
    """Для 1/2/3/4/6 — курируемая латынь; для прочих — корректный русский фолбэк."""
    verdict = _run(
        r"""(() => ({
          one: formatFrequency(1, 'latin'),
          two: formatFrequency(2, 'latin'),
          three: formatFrequency(3, 'latin'),
          six: formatFrequency(6, 'latin'),
          eight: formatFrequency(8, 'latin'),
          short: formatFrequency(8, 'short'),
        }))()"""
    )

    assert verdict["one"] == "semel in die", verdict
    assert verdict["three"] == "ter in die", verdict
    assert verdict["six"] == "sexies in die", verdict
    assert verdict["eight"] == "8 раз в день", verdict
    assert verdict["short"] == "8 р/д", verdict


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
