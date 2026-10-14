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


# ── service-worker cache version (audit 2026-10-14, H-2) ─────────────────────
SW_PATH = ROOT / "sw.js"


def test_service_worker_cache_version_tracks_the_shell_and_its_assets() -> None:
    """A rebuilt shell with an unchanged `CACHE_VERSION` would be served from the
    stale offline cache forever. The version is generated by the build; this
    pins it to the committed artifacts so a forgotten rebuild fails CI."""
    current, expected = build_html_module.expected_service_worker_version(SW_PATH, ARTIFACT_PATH)
    assert current == expected, (
        f"sw.js CACHE_VERSION {current!r} is stale for the committed shell/assets "
        f"(expected {expected!r}); run `python db/build_html.py`"
    )
    assert current.startswith("build-")


def test_service_worker_cache_version_changes_with_the_shell_or_an_asset(tmp_path: Path) -> None:
    sw_text = SW_PATH.read_text(encoding="utf-8")
    base = build_html_module.service_worker_cache_version("<html>a</html>", sw_text, ROOT)
    assert base == build_html_module.service_worker_cache_version("<html>a</html>", sw_text, ROOT)
    assert base != build_html_module.service_worker_cache_version("<html>b</html>", sw_text, ROOT)
    # a precached asset that changes (or appears) must rotate the cache too
    root = tmp_path
    (root / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    one = build_html_module.service_worker_cache_version("<html>a</html>", sw_text, root)
    (root / "manifest.webmanifest").write_text('{"name":"x"}', encoding="utf-8")
    two = build_html_module.service_worker_cache_version("<html>a</html>", sw_text, root)
    assert one != two
    # an unrelated file that the worker does not precache does not matter
    (root / "unrelated.txt").write_text("x", encoding="utf-8")
    assert two == build_html_module.service_worker_cache_version("<html>a</html>", sw_text, root)


def test_sync_service_worker_rewrites_only_the_version_line(tmp_path: Path) -> None:
    sw = tmp_path / "sw.js"
    shell = tmp_path / "antibiotic_calc.html"
    shell.write_text("<html>shell</html>", encoding="utf-8")
    original = SW_PATH.read_text(encoding="utf-8")
    sw.write_text(original, encoding="utf-8")
    report = build_html_module.sync_service_worker(sw, shell)
    assert report["changed"] is True and report["current"].startswith("build-")
    updated = sw.read_text(encoding="utf-8")
    assert f"const CACHE_VERSION = '{report['current']}';" in updated
    # byte-identical apart from that single line
    diff = [(a, b) for a, b in zip(original.splitlines(), updated.splitlines()) if a != b]
    assert len(diff) == 1 and diff[0][0].startswith("const CACHE_VERSION")
    assert len(original.splitlines()) == len(updated.splitlines())
    # idempotent
    assert build_html_module.sync_service_worker(sw, shell)["changed"] is False


def test_building_elsewhere_never_touches_the_repo_service_worker(tmp_path: Path) -> None:
    """Only a build of the real shell may re-stamp the repo's sw.js."""
    before = SW_PATH.read_bytes()
    report = build_html_module.build_html(
        db_path=DB_PATH, template_path=TEMPLATE_PATH,
        output_path=tmp_path / "antibiotic_calc.html", run_validate=False,
    )
    assert report["service_worker"] is None
    assert SW_PATH.read_bytes() == before


def test_check_mode_reports_fresh_for_the_committed_artifacts() -> None:
    """`python db/build_html.py --check` is the pre-commit/CI freshness gate."""
    assert build_html_module.check_build(run_validate=False) == []


def test_check_mode_detects_a_stale_shell_and_a_stale_service_worker(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path) -> None:
    repo_html = tmp_path / "antibiotic_calc.html"
    repo_sw = tmp_path / "sw.js"
    repo_html.write_bytes(ARTIFACT_PATH.read_bytes() + b"\n<!-- hand edit -->")
    repo_sw.write_text(SW_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(build_html_module, "OUTPUT_PATH", repo_html)
    monkeypatch.setattr(build_html_module, "SERVICE_WORKER_PATH", repo_sw)
    problems = build_html_module.check_build(run_validate=False)
    assert any("antibiotic_calc.html is stale" in p for p in problems)
    assert any("sw.js CACHE_VERSION" in p for p in problems)
    # check mode never repairs anything by itself
    assert repo_html.read_bytes().endswith(b"<!-- hand edit -->")
    assert "const CACHE_VERSION = 'build-" in repo_sw.read_text(encoding="utf-8")


def test_cli_check_flag_exit_codes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    assert build_html_module.main(["--check", "--skip-validate"]) == 0
    assert "Build is fresh" in capsys.readouterr().out
    monkeypatch.setattr(build_html_module, "check_build", lambda **_: ["sw.js CACHE_VERSION 'v4' is stale"])
    assert build_html_module.main(["--check", "--skip-validate"]) == 1
    assert "STALE: sw.js" in capsys.readouterr().err


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
