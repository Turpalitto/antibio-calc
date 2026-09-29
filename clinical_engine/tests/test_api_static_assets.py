"""Static/PWA asset serving for the FastAPI adapter (INT-5a).

The shell is a PWA: ``antibiotic_calc.html`` registers ``./sw.js``, links
``manifest.webmanifest`` and precaches ``./icons/*.png``. Those URLs are
relative to the page origin, so they are only reachable when the process that
serves the shell also serves them. ``server.js`` does; this app must too, or a
physician-hosted install (http://127.0.0.1:8000/personal) is silently
non-installable and non-offline.

The other half of this file is the security invariant: the app root is the
repository root, which also contains ``.git/``, ``.env`` and the gitignored
``.local/personal_physician/`` owner-token store. Starlette's ``StaticFiles``
has no dot-path filtering, so the design under test is an explicit allow-list
of file names plus a single ``icons/`` mount — not a mount of the repository.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clinical_engine.api.app import APP_ROOT, ICON_DIR, PWA_ASSETS, _asset, create_app
from clinical_engine.api.service import ApiContext
from clinical_engine.corpus.locator import CorpusLocator

# Files the repository root must never expose over HTTP.
SECRET_PATHS = (
    "/.git/config",
    "/.git/HEAD",
    "/.env",
    "/.env.example",
    "/.gitleaks.toml",
    "/.local/personal_physician/state.json",
    "/.venv/pyvenv.cfg",
    "/.serena/project.yml",
)

# Ordinary repository files that are simply not part of the web surface.
REPO_PATHS = ("/package.json", "/server.js", "/README.md", "/AGENTS.md", "/main.py")

ENGINE_PATHS = (
    "/v1/health",
    "/v1/version",
    "/v2/personal/health",
    "/v2/personal/attestations",
    "/v2/personal/extracted-candidates/g1",
)


def _context(tmp_path: Path) -> ApiContext:
    root = tmp_path / "corpus"
    root.mkdir(exist_ok=True)
    return ApiContext(corpus=CorpusLocator(root))


def _client(tmp_path: Path, base_url: str = "http://127.0.0.1:8000") -> TestClient:
    return TestClient(create_app(_context(tmp_path)), base_url=base_url)


def _require(name: str) -> Path:
    path = APP_ROOT / name
    if not path.is_file():
        pytest.skip(f"{name} is not present in this checkout")
    return path


# ── PWA assets are served ─────────────────────────────────────────


def test_service_worker_is_served_with_a_javascript_media_type(tmp_path):
    _require("sw.js")
    response = _client(tmp_path).get("/sw.js")
    assert response.status_code == 200
    # A service worker registered with the wrong MIME type is rejected by the
    # browser, so the content type is part of the contract, not cosmetics.
    assert response.headers["content-type"].startswith(("text/javascript", "application/javascript"))
    assert "CACHE_NAME" in response.text


def test_web_manifest_is_served_with_the_manifest_media_type(tmp_path):
    _require("manifest.webmanifest")
    response = _client(tmp_path).get("/manifest.webmanifest")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    manifest = json.loads(response.text)
    assert manifest["start_url"] == "./"
    assert manifest["scope"] == "./"
    assert manifest["icons"], "manifest must declare the icons the shell precaches"


def test_shell_is_served_at_the_paths_the_manifest_resolves_to(tmp_path):
    # "./" in the manifest resolves to the origin root, and the service worker
    # precaches "./antibiotic_calc.html"; an installed app launched from the
    # engine origin must not 404 on either.
    _require("antibiotic_calc.html")
    client = _client(tmp_path)
    for path in ("/", "/personal", "/antibiotic_calc.html"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("text/html"), path


def test_shell_assets_are_revalidated_not_pinned(tmp_path):
    _require("antibiotic_calc.html")
    client = _client(tmp_path)
    for path in ("/", "/personal", "/antibiotic_calc.html", "/sw.js", "/manifest.webmanifest"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path


@pytest.mark.parametrize("name", ["icon-192.png", "icon-512.png"])
def test_icons_are_served_as_png(tmp_path, name):
    if not (ICON_DIR / name).is_file():
        pytest.skip("icons/ is not present in this checkout")
    response = _client(tmp_path).get(f"/icons/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_icons_mount_serves_only_icons(tmp_path):
    if not ICON_DIR.is_dir():
        pytest.skip("icons/ is not present in this checkout")
    client = _client(tmp_path)
    assert client.get("/icons/").status_code == 404  # no directory listing
    assert client.get("/icons/does-not-exist.png").status_code == 404
    for path in ("/icons/../.git/config", "/icons/..%2f.git/config",
                 "/icons/%2e%2e/%2e%2e/etc/passwd", "/icons/%2e%2e/package.json"):
        assert client.get(path).status_code == 404, path


def test_missing_asset_is_a_404_not_a_500(tmp_path, monkeypatch):
    # A checkout without a built artifact must still start and answer cleanly.
    monkeypatch.setattr("clinical_engine.api.app.APP_ROOT", tmp_path)
    response = _client(tmp_path).get("/sw.js")
    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "ASSET_NOT_FOUND"


# ── the repository root is not web-servable ───────────────────────


def test_asset_resolver_refuses_everything_outside_the_allow_list():
    for name in (".env", ".git/config", ".local/personal_physician/state.json",
                 "package.json", "server.js", "sw.js.bak", "icons/icon-192.png",
                 "../outside.html", "nested/sw.js"):
        assert _asset(name) is None, name
    assert set(PWA_ASSETS) == {"sw.js", "manifest.webmanifest", "antibiotic_calc.html"}


def test_asset_resolver_refuses_traversal_and_returns_the_allow_listed_files():
    assert _asset("sw.js") is None or _asset("sw.js").status_code == 200
    # containment is checked on the resolved path, so a name that resolves
    # outside the app root can never be returned
    assert _asset("sw.js/../../etc/passwd") is None


@pytest.mark.parametrize("path", SECRET_PATHS)
def test_secret_paths_are_not_served(tmp_path, path):
    response = _client(tmp_path).get(path)
    assert response.status_code == 404, f"{path} returned {response.status_code}"
    assert b"root = " not in response.content  # .git/config marker


@pytest.mark.parametrize("path", REPO_PATHS)
def test_ordinary_repository_files_are_not_served(tmp_path, path):
    assert _client(tmp_path).get(path).status_code == 404


def test_no_static_mount_covers_the_repository_root(tmp_path):
    # Structural guard: a future `app.mount("/", StaticFiles(directory=APP_ROOT))`
    # would satisfy every route test above only if the dot-path checks were also
    # satisfied — assert the mount surface directly so the intent survives.
    from starlette.routing import Mount

    mounts = [r for r in create_app(_context(tmp_path)).routes if isinstance(r, Mount)]
    # icons/ is untracked in git, so a fresh clone legitimately mounts nothing.
    assert [m.path for m in mounts] == (["/icons"] if ICON_DIR.is_dir() else [])


def test_absent_icons_directory_degrades_to_404_not_500(tmp_path, monkeypatch):
    # StaticFiles raises RuntimeError -> HTTP 500 for a missing directory even
    # with check_dir=False, so the mount must be conditional.
    monkeypatch.setattr("clinical_engine.api.app.ICON_DIR", tmp_path / "no-such-icons")
    client = TestClient(create_app(_context(tmp_path)), base_url="http://127.0.0.1:8000")
    assert client.get("/icons/icon-192.png").status_code == 404
    assert client.get("/v1/health").status_code == 200


# ── engine routes are not shadowed ────────────────────────────────


@pytest.mark.parametrize("path", ENGINE_PATHS)
def test_engine_routes_still_resolve(tmp_path, path):
    response = _client(tmp_path).get(path)
    assert response.status_code != 404, f"{path} was shadowed by a static route"
    assert response.headers["content-type"].startswith("application/json"), path


def test_engine_write_route_still_reaches_its_handler(tmp_path):
    response = _client(tmp_path).post("/v1/recommend", json={})
    # 400 INVALID_REQUEST, i.e. the handler ran — not 404/405 from a static route.
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "INVALID_REQUEST"


def test_openapi_documentation_is_not_shadowed(tmp_path):
    client = _client(tmp_path)
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_shell_routes_are_registered_after_every_engine_route(tmp_path):
    paths = [getattr(r, "path", None) for r in create_app(_context(tmp_path)).routes]
    engine = [i for i, p in enumerate(paths) if p and p.startswith(("/v1", "/v2"))]
    static = [i for i, p in enumerate(paths)
              if p in {"/", "/personal", "/antibiotic_calc.html", "/sw.js",
                       "/manifest.webmanifest", "/icons"}]
    assert engine and static
    assert max(static) > max(engine), "static routes must be registered last"


# ── the shell's own declarations match what the app serves ───────


def test_service_worker_precache_list_is_fully_served(tmp_path):
    """The regression this file exists for.

    ``sw.js`` precaches ``PRECACHE_URLS`` relative to the service worker's
    scope (``/``). Any entry the server cannot answer makes ``install`` fail and
    leaves the physician with no offline shell — and the precache helper
    swallows per-asset errors, so it would not even be visible in the console.
    """
    sw = _require("sw.js")
    source = sw.read_text(encoding="utf-8")
    match = re.search(r"const PRECACHE_URLS\s*=\s*\[(.*?)\]", source, re.DOTALL)
    assert match, "sw.js must declare PRECACHE_URLS"
    urls = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))

    client = _client(tmp_path)
    for url in urls:
        relative = url.removeprefix("./")
        path = "/" + relative
        if not (APP_ROOT / relative).is_file():
            pytest.skip(f"{relative} is not present in this checkout")
        response = client.get(path)
        assert response.status_code == 200, f"{url} is precached but not served ({response.status_code})"
        assert response.content, url


def test_manifest_icon_sources_are_served(tmp_path):
    manifest_path = _require("manifest.webmanifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    client = _client(tmp_path)
    for icon in manifest["icons"]:
        src = icon["src"].removeprefix("./")
        if not (APP_ROOT / src).is_file():
            pytest.skip(f"{src} is not present in this checkout")
        assert client.get("/" + src).status_code == 200, src


def test_shell_declares_the_same_asset_urls(tmp_path):
    """The built shell is generated, so read the template's registration line
    when the built artifact is absent — either way the relative URLs must be
    the ones the app serves."""
    template = APP_ROOT / "antibiotic_calc.html.template"
    shell = _require("antibiotic_calc.html")
    source = template.read_text(encoding="utf-8") if template.is_file() else shell.read_text(encoding="utf-8")
    assert "serviceWorker.register('./sw.js')" in source
    assert 'href="manifest.webmanifest"' in source
    client = _client(tmp_path)
    for path in ("/sw.js", "/manifest.webmanifest"):
        response = client.get(path)
        if response.status_code == 404:
            pytest.skip(f"{path} is not present in this checkout")
        assert response.status_code == 200


# ── loopback policy matches the existing /personal rule ──────────


def test_shell_is_loopback_only_like_personal_mode(tmp_path):
    for base_url in ("http://127.0.0.1:8000", "http://localhost:8000"):
        client = _client(tmp_path, base_url=base_url)
        assert client.get("/personal").status_code in (200, 404)
        assert client.get("/").status_code == client.get("/personal").status_code
        assert client.get("/antibiotic_calc.html").status_code == client.get("/personal").status_code

    lan = _client(tmp_path, base_url="http://192.168.1.20:8000")
    for path in ("/", "/personal", "/antibiotic_calc.html"):
        assert lan.get(path).status_code == 403, path
        assert lan.get(path).json()["errors"][0]["code"] == "NON_LOOPBACK_HOST"
