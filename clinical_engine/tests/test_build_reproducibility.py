"""Build-drift guard for the committed calculator artifact.

`antibiotic_calc.html` is a 680 KB *committed* artifact and it is the file the
FastAPI app actually serves (`/personal`, `CALCULATOR_BUILD_MISSING`). Nothing
else in the test suite compared the artifact with its inputs, so a hand edit or
a failed partial build could ship divergent clinical data with a green test run.

These tests rebuild the artifact from `antibiotic_calc.html.template` +
`db/antibio_db.json` through the *same* code path as `db/build_html.py` and assert
it is byte-identical to the committed file.

Known consequence: this legitimately FAILS whenever the template is edited
without a rebuild. That is the point — rebuild with `npm run build`
(`python db/build_html.py`) and re-run.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / "antibiotic_calc.html.template"
DB_PATH = ROOT / "db" / "antibio_db.json"
ARTIFACT_PATH = ROOT / "antibiotic_calc.html"
BUILD_SCRIPT_PATH = ROOT / "db" / "build_html.py"

# The single element the build script fills; mirrors the template contract.
DB_SCRIPT_RE = re.compile(
    r'<script id="db-data" type="application/json">(?P<payload>.*?)</script>',
    re.DOTALL,
)


def _load_build_module():
    """Import `db/build_html.py` by path (`db/` is a namespace package)."""
    spec = importlib.util.spec_from_file_location("antibio_build_html", BUILD_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


build_html_module = _load_build_module()


@pytest.fixture(scope="module")
def rebuild(tmp_path_factory) -> Path:
    """Rebuild the artifact once per module through the real build code path."""
    out = tmp_path_factory.mktemp("rebuild") / "antibiotic_calc.html"
    build_html_module.build_html(
        db_path=DB_PATH,
        template_path=TEMPLATE_PATH,
        output_path=out,
        run_validate=True,
    )
    return out


@pytest.fixture(scope="module")
def committed() -> bytes:
    assert ARTIFACT_PATH.is_file(), f"missing committed artifact: {ARTIFACT_PATH}"
    return ARTIFACT_PATH.read_bytes()


def test_committed_artifact_is_byte_identical_to_rebuild(rebuild: Path, committed: bytes) -> None:
    rebuilt = rebuild.read_bytes()
    assert hashlib.sha256(rebuilt).hexdigest() == hashlib.sha256(committed).hexdigest(), (
        "antibiotic_calc.html is stale or hand-edited: it does not match a rebuild "
        f"from the template + db/antibio_db.json "
        f"(rebuild {hashlib.sha256(rebuilt).hexdigest()[:12]} != "
        f"committed {hashlib.sha256(committed).hexdigest()[:12]}). "
        "Run: python db/build_html.py"
    )
    assert rebuilt == committed, "rebuilt and committed artifacts differ in bytes"


def test_artifact_has_no_bom_and_no_trailing_whitespace(committed: bytes) -> None:
    assert not committed.startswith(b"\xef\xbb\xbf"), "artifact must be UTF-8 without BOM"
    assert committed == committed.strip(), "artifact must not carry leading/trailing whitespace"


def test_db_placeholder_appears_exactly_once() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert template.count(build_html_module.PLACEHOLDER) == 1, (
        f"template must contain exactly one {build_html_module.PLACEHOLDER} marker"
    )
    assert build_html_module.PLACEHOLDER not in ARTIFACT_PATH.read_text(encoding="utf-8"), (
        "unsubstituted placeholder left in the artifact"
    )


def test_injected_payload_cannot_break_out_of_script_tag(committed: bytes) -> None:
    html = committed.decode("utf-8")
    match = DB_SCRIPT_RE.search(html)
    assert match is not None, "no <script id=\"db-data\"> element found in the artifact"
    payload = match.group("payload")
    assert "</script" not in payload.lower(), (
        "injected DB payload contains a </script> sequence and would break out of the "
        "db-data script element"
    )
    # The payload must be the DB verbatim, so a doctor sees exactly the validated data.
    assert json.loads(payload) == json.loads(DB_PATH.read_text(encoding="utf-8-sig"))
    assert payload.count('"recommendations"') == 1


def test_build_stamp_is_deterministic(rebuild: Path) -> None:
    db_text = DB_PATH.read_text(encoding="utf-8-sig").strip()
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    first = build_html_module.build_stamp(db_text, template_text)
    second = build_html_module.build_stamp(db_text, template_text)
    assert first == second, "build stamp must depend only on the inputs, never on wall-clock time"
    assert first.startswith("db:") and "tpl:" in first


def test_build_refuses_template_without_marker(tmp_path: Path) -> None:
    bad_template = tmp_path / "tpl.html"
    bad_template.write_text("<html>no marker here</html>", encoding="utf-8")
    with pytest.raises(build_html_module.BuildError):
        build_html_module.build_html(
            db_path=DB_PATH,
            template_path=bad_template,
            output_path=tmp_path / "out.html",
            run_validate=False,
        )
    assert not (tmp_path / "out.html").exists(), "a failed build must not write an artifact"


def test_build_refuses_payload_with_script_breakout(tmp_path: Path) -> None:
    poisoned = tmp_path / "db.json"
    poisoned.write_text(
        json.dumps(
            {
                "meta": {},
                "drugs_reference": {},
                "categories": [],
                "recommendations": [],
                "x": "</script><script>alert(1)</script>",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(build_html_module.BuildError):
        build_html_module.build_html(
            db_path=poisoned,
            template_path=TEMPLATE_PATH,
            output_path=tmp_path / "out.html",
            run_validate=False,
        )
    assert not (tmp_path / "out.html").exists()


def test_build_is_missing_node_loudly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A validator that cannot run must fail the build, not silently skip it."""
    monkeypatch.setenv("PATH", "")
    with pytest.raises(build_html_module.BuildError, match="not found"):
        build_html_module.build_html(
            run_validate=True,
            output_path=tmp_path / "must-not-exist.html",
        )
    assert not (tmp_path / "must-not-exist.html").exists()
