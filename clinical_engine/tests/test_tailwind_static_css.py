"""Static Tailwind build for the calculator shell (audit 2026-10-14, H-1).

Until 2026-10-14 the shell loaded ``vendor/tailwind.js`` — the Tailwind
**Play CDN** (a 407 KB JIT compiler that scans the DOM and generates CSS in
the browser on every launch; Tailwind itself labels it "not for production").
It was replaced by ``vendor/app.css``: the same Tailwind line (3.4.17) run
once over the template (``db/tailwind.config.cjs``, ``npm run build:css``).

The Play CDN generated classes from the live DOM, the static build generates
them from the template text. That is only equivalent while every class the
shell can ever put in the DOM appears as a literal token in the template —
which is why these tests exist:

* every class token in the template (markup *and* JS string literals) that is
  not a custom class from the inline ``<style>`` and not a Font Awesome class
  must have a rule in ``vendor/app.css`` — otherwise somebody edited the
  template and forgot ``npm run build:css`` (the drift this file guards);
* the shell links the static stylesheet and no longer references the CDN
  compiler; the service worker precaches the stylesheet (offline shell);
* when the pinned CLI is installed (``npm ci`` at the repo root), rebuilding
  the stylesheet reproduces the committed file byte for byte.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = PROJECT_ROOT / "antibiotic_calc.html.template"
APP_CSS = PROJECT_ROOT / "vendor" / "app.css"
SERVICE_WORKER = PROJECT_ROOT / "sw.js"
TAILWIND_CONFIG = PROJECT_ROOT / "db" / "tailwind.config.cjs"
TAILWIND_INPUT = PROJECT_ROOT / "db" / "tailwind.input.css"

# Tokens that look like classes but that Tailwind 3.4 cannot generate and no
# stylesheet defines. They were no-ops under the Play CDN as well, so the static
# build changes nothing for them; they are listed so the drift check stays exact.
#   md:pl-13  — `13` is not in Tailwind's default spacing scale
#   no-print  — never defined (the print stylesheet uses `body>*`)
#   num-glow  — never defined
KNOWN_NO_OPS = frozenset({"md:pl-13", "no-print", "num-glow"})

_CLASS_ATTR_RE = re.compile(r"""class=(?:\\?["'])([^"'<>]*?)(?:\\?["'])""")
_CLASS_JS_RE = re.compile(
    r"""(?:className\s*(?:=|\+=)\s*|classList\.(?:add|remove|toggle|replace)\()\s*"""
    r"""((?:["'][^"']*["']\s*[,+]?\s*)+)"""
)
_JS_STRING_RE = re.compile(r"""["']([^"'\n]*)["']""")
_CSS_CLASS_RE = re.compile(r"\.((?:\\.|[A-Za-z0-9_-])+)")
_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
_UTILITY_PREFIXES = (
    "bg|text|border|ring|rounded|p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|flex|grid|gap|w|h|min|max|opacity|"
    "shadow|font|tracking|items|justify|space|divide|animate|transition|duration|overflow|whitespace|leading|z|"
    "top|left|right|bottom|inset|cursor|select|pointer|col|row|order|self|place|translate|scale|rotate|line|"
    "list|outline|sr|dark|sm|md|lg|xl|grow|shrink|basis|object|resize|backdrop|"
    "blur|from|to|via|fill|stroke|accent|caret|decoration|break|aspect|columns|float|clear|table|mix|drop|snap|"
    "touch|will|content|group|peer|tabular|normal"
)
_UTILITY_SHAPE_RE = re.compile(
    r"^(?:[a-z]+:)*-?(?:" + _UTILITY_PREFIXES + r")(?:-[a-z0-9\[\]./%]+)+(?:/\d+)?$"
    r"|^(?:[a-z]+:)*(?:flex|grid|hidden|block|inline|italic|uppercase|lowercase|capitalize|truncate|underline|"
    r"relative|absolute|fixed|sticky|invisible|visible|contents|isolate|container|antialiased|tabular-nums)$"
)


def _template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _template_class_tokens(template: str) -> set[str]:
    """Every class token Tailwind's extractor would see in the template.

    `class="…"` attributes anywhere in the file (static markup and JS template
    strings alike), the string literals handed to `className` / `classList`,
    and any other string literal that consists solely of utility-shaped words —
    those are the fragments the shell concatenates into `className` at runtime
    (``cardAllergyClass``, ``lineCls`` …).
    """
    tokens: set[str] = set()
    for match in _CLASS_ATTR_RE.finditer(template):
        tokens.update(match.group(1).split())
    for match in _CLASS_JS_RE.finditer(template):
        for literal in _JS_STRING_RE.findall(match.group(1)):
            tokens.update(literal.split())
    for literal in _JS_STRING_RE.findall(template):
        words = literal.split()
        if 1 <= len(words) <= 12 and all(_UTILITY_SHAPE_RE.match(w) for w in words):
            tokens.update(words)
    return {t for t in tokens if t and "${" not in t and "+" not in t}


def _custom_classes(template: str) -> set[str]:
    style = " ".join(_STYLE_BLOCK_RE.findall(template))
    return {m.group(1) for m in _CSS_CLASS_RE.finditer(style)}


def _css_classes(css: str) -> set[str]:
    return {re.sub(r"\\(.)", r"\1", m.group(1)) for m in _CSS_CLASS_RE.finditer(css)}


def _is_font_awesome(token: str) -> bool:
    return token in {"fa", "fas", "far", "fab", "fa-fw", "fa-spin"} or token.startswith("fa-")


def test_static_stylesheet_exists_and_is_a_tailwind_build() -> None:
    assert APP_CSS.is_file(), "vendor/app.css missing — run `npm ci && npm run build:css`"
    css = APP_CSS.read_text(encoding="utf-8")
    assert len(css) > 10_000, "vendor/app.css is suspiciously small — not a full Tailwind build"
    assert "tailwindcss v3.4.17" in css, "vendor/app.css must be built with the pinned Tailwind 3.4.17"
    # preflight (base layer) and the class-strategy dark mode the Play CDN was configured with
    assert "--tw-ring-offset-shadow" in css
    assert ":is(.dark *)" in css, "darkMode:'class' lost — dark theme would stop working"
    assert "@media (min-width:768px)" in css, "md: breakpoint missing"


def test_shell_links_static_stylesheet_and_not_the_play_cdn() -> None:
    template = _template_text()
    assert '<link href="./vendor/app.css" rel="stylesheet">' in template
    assert "vendor/tailwind.js" not in template
    assert "cdn.tailwindcss.com" not in template
    assert "tailwind.config =" not in template, "runtime Tailwind config has no effect without the CDN compiler"
    assert not (PROJECT_ROOT / "vendor" / "tailwind.js").exists(), "Play CDN bundle must not come back"


def test_tailwind_config_matches_the_former_cdn_setup() -> None:
    config = TAILWIND_CONFIG.read_text(encoding="utf-8")
    assert 'content: ["./antibiotic_calc.html.template"]' in config
    assert 'darkMode: "class"' in config
    assert TAILWIND_INPUT.read_text(encoding="utf-8").count("@tailwind") == 3


def test_service_worker_precaches_the_stylesheet() -> None:
    sw = SERVICE_WORKER.read_text(encoding="utf-8")
    assert "'./vendor/app.css'" in sw
    assert "'./vendor/tailwind.js'" not in sw


def test_every_template_class_has_a_rule_in_the_static_stylesheet() -> None:
    template = _template_text()
    tokens = _template_class_tokens(template)
    assert len(tokens) > 300, "class extraction broke — far fewer tokens than the shell uses"
    css_classes = _css_classes(APP_CSS.read_text(encoding="utf-8"))
    custom = _custom_classes(template)
    missing = sorted(
        t
        for t in tokens
        if t not in css_classes and t not in custom and not _is_font_awesome(t) and t not in KNOWN_NO_OPS
    )
    assert not missing, (
        "classes used by the shell but absent from vendor/app.css — run `npm run build:css` "
        f"(and commit the result): {missing}"
    )
    # the allowlist must not hide classes that are generated after all
    stale = sorted(t for t in KNOWN_NO_OPS if t in css_classes or t in custom)
    assert not stale, f"KNOWN_NO_OPS entries now have rules, drop them from the list: {stale}"


def _tailwind_cli() -> str | None:
    local = PROJECT_ROOT / "node_modules" / ".bin" / ("tailwindcss.cmd" if os.name == "nt" else "tailwindcss")
    if local.exists():
        return str(local)
    return shutil.which("tailwindcss")


@pytest.mark.skipif(_tailwind_cli() is None, reason="tailwindcss CLI not installed (npm ci at the repo root)")
def test_committed_stylesheet_is_reproducible(tmp_path: Path) -> None:
    """`npm run build:css` must reproduce vendor/app.css exactly (no local drift)."""
    out = tmp_path / "app.css"
    cmd = [
        _tailwind_cli(),
        "-c",
        str(TAILWIND_CONFIG),
        "-i",
        str(TAILWIND_INPUT),
        "-o",
        str(out),
        "--minify",
    ]
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300,
                          shell=(os.name == "nt" and sys.platform == "win32"))
    assert proc.returncode == 0, proc.stderr[-2000:]
    rebuilt = out.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    committed = APP_CSS.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    assert rebuilt == committed, "vendor/app.css is stale — run `npm run build:css` and commit it"
