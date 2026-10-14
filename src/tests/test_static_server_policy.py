"""`server.js` serving and proxy policy (audit 2026-10-14, findings C-1 / C-3).

The Node static server is the recommended way to run the calculator locally and
the only component that sits in front of the clinical engine. These tests start
the real `server.js` on an ephemeral port and pin:

* the static allowlist — repository files (`package.json`, `REPOSITORY_MANIFEST.json`,
  `server.js`, …) are refused even though their extension is "allowed";
* the proxy peer policy — engine paths are forwarded for loopback clients only
  (a LAN peer gets 403 PROXY_LOOPBACK_ONLY instead of being laundered into a
  127.0.0.1 request towards the engine's physician-mode gate);
* the request-body cap — 413 before anything reaches the engine.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required to run server.js")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_listening(host: str, port: int, proc: subprocess.Popen, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"server.js exited early: {proc.stderr.read() if proc.stderr else ''}")
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("server.js did not start listening")


def _request(host: str, port: int, method: str, path: str, body: bytes | None = None, headers: dict | None = None):
    conn = http.client.HTTPConnection(host, port, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, dict(resp.getheaders()), data
    finally:
        conn.close()


@pytest.fixture(scope="module")
def loopback_server():
    port = _free_port()
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1",
           # point the engine at a closed port so proxied requests fail fast with 502
           "ENGINE_BASE_URL": f"http://127.0.0.1:{_free_port()}",
           "ENGINE_MAX_BODY_BYTES": "2048"}
    proc = subprocess.Popen([NODE, str(SERVER)], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _wait_listening("127.0.0.1", port, proc)
        yield "127.0.0.1", port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _non_loopback_ipv4() -> str | None:
    try:
        import psutil  # dependency of the engine, present in the locked env
    except ImportError:  # pragma: no cover - psutil is locked, but stay honest
        return None
    for addrs in psutil.net_if_addrs().values():
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                return addr.address
    return None


@pytest.fixture(scope="module")
def lan_server():
    ip = _non_loopback_ipv4()
    if ip is None:
        pytest.skip("no non-loopback IPv4 interface available to simulate a LAN peer")
    port = _free_port()
    env = {**os.environ, "PORT": str(port), "HOST": "0.0.0.0",
           "ENGINE_BASE_URL": f"http://127.0.0.1:{_free_port()}"}
    proc = subprocess.Popen([NODE, str(SERVER)], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _wait_listening("127.0.0.1", port, proc)
        yield ip, port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---- static allowlist -----------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/antibiotic_calc.html", "/sw.js", "/manifest.webmanifest",
                                  "/icons/icon-192.png", "/vendor/tailwind.js"])
def test_app_assets_are_served(loopback_server, path) -> None:
    host, port = loopback_server
    status, headers, body = _request(host, port, "GET", path)
    assert status == 200, (path, status, body[:120])
    assert headers.get("X-Content-Type-Options") == "nosniff"
    if path in ("/", "/antibiotic_calc.html"):
        assert "Content-Security-Policy" in headers
        assert b"db-data" in body


@pytest.mark.parametrize("path,code", [
    ("/package.json", "FORBIDDEN_PATH"),
    ("/REPOSITORY_MANIFEST.json", "FORBIDDEN_PATH"),
    ("/server.js", "FORBIDDEN_PATH"),
    ("/antibiotic_calc.html.template", "FORBIDDEN_EXTENSION"),
    ("/README.md", "FORBIDDEN_EXTENSION"),
    ("/db/antibio_db.json", "FORBIDDEN_PATH"),
    ("/clinical_engine/api/app.py", "FORBIDDEN_EXTENSION"),
    ("/.env", "FORBIDDEN_PATH"),
    ("/.git/config", "FORBIDDEN_PATH"),
    # URL parsing already collapses "/../" (the server's own ".." guard is a
    # second line); either way the answer is a refusal, never a file.
    ("/../etc/passwd", {"PATH_TRAVERSAL", "FORBIDDEN_EXTENSION", "FORBIDDEN_PATH"}),
    ("/%2e%2e/etc/passwd", {"PATH_TRAVERSAL", "FORBIDDEN_EXTENSION", "FORBIDDEN_PATH"}),
])
def test_repository_files_are_refused(loopback_server, path, code) -> None:
    host, port = loopback_server
    status, _headers, body = _request(host, port, "GET", path)
    assert status in (400, 403), (path, status)
    expected = code if isinstance(code, set) else {code}
    assert json.loads(body)["error"] in expected


def test_static_paths_reject_write_methods(loopback_server) -> None:
    host, port = loopback_server
    status, headers, _ = _request(host, port, "POST", "/antibiotic_calc.html", body=b"{}")
    assert status == 405 and headers.get("Allow") == "GET, HEAD"


# ---- engine proxy policy -------------------------------------------------------------


def test_loopback_peer_reaches_the_proxy_and_gets_engine_unavailable(loopback_server) -> None:
    host, port = loopback_server
    status, _headers, body = _request(host, port, "GET", "/v1/health")
    assert status == 502
    assert json.loads(body)["error"] == "ENGINE_UNAVAILABLE"


def test_proxy_refuses_oversized_bodies_before_the_engine(loopback_server) -> None:
    host, port = loopback_server
    payload = b"x" * 4096  # cap for this server is 2048
    status, _headers, body = _request(host, port, "POST", "/v1/recommend", body=payload,
                                      headers={"Content-Type": "application/json"})
    assert status == 413
    assert json.loads(body)["error"] == "PAYLOAD_TOO_LARGE"


def test_lan_peer_gets_the_shell_but_not_the_engine_proxy(lan_server) -> None:
    ip, port = lan_server
    status, _headers, body = _request(ip, port, "GET", "/antibiotic_calc.html")
    assert status == 200 and b"db-data" in body
    status, _headers, body = _request(ip, port, "GET", "/v1/health")
    assert status == 403, body[:200]
    assert json.loads(body)["error"] == "PROXY_LOOPBACK_ONLY"
    status, _headers, body = _request(ip, port, "POST", "/v2/personal/session", body=b"{}",
                                      headers={"Content-Type": "application/json"})
    assert status == 403 and json.loads(body)["error"] == "PROXY_LOOPBACK_ONLY"


def test_is_loopback_address_helper() -> None:
    script = (
        "const s=require(process.argv[1]);"
        "console.log(JSON.stringify(['127.0.0.1','127.0.0.2','::1','::ffff:127.0.0.1','192.168.1.5','::ffff:192.168.1.5','10.0.0.1','',null,'localhost']"
        ".map(s.isLoopbackAddress)));"
    )
    out = subprocess.run([NODE, "-e", script, str(SERVER)], capture_output=True, text=True, check=True, cwd=ROOT)
    assert json.loads(out.stdout) == [True, True, True, True, False, False, False, False, False, True]


def test_resolve_static_file_allowlist_is_explicit() -> None:
    script = (
        "const s=require(process.argv[1]);"
        "const probe=p=>{const r=s.resolveStaticFile(p);return r.status===200?'ok':r.code;};"
        "console.log(JSON.stringify({root:[...s.ROOT_FILES],dirs:[...s.ALLOWED_DIRS],"
        "probes:['/','/antibiotic_calc.html','/sw.js','/package.json','/vendor/css/x.css','/icons/icon-192.png','/db/x.json','/x.html'].map(probe)}));"
    )
    out = subprocess.run([NODE, "-e", script, str(SERVER)], capture_output=True, text=True, check=True, cwd=ROOT)
    result = json.loads(out.stdout)
    assert set(result["root"]) == {"/antibiotic_calc.html", "/sw.js", "/manifest.webmanifest", "/favicon.ico"}
    assert set(result["dirs"]) == {"icons", "vendor"}
    assert result["probes"] == ["ok", "ok", "ok", "FORBIDDEN_PATH", "ok", "ok", "FORBIDDEN_PATH", "FORBIDDEN_PATH"]


if sys.platform.startswith("win"):  # pragma: no cover - documented limitation
    pytest.skip("server.js policy tests assume POSIX sockets", allow_module_level=True)
