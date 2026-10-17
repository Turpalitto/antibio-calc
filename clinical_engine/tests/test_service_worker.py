"""Behaviour of the offline service worker (``sw.js``).

Until 2026-10-14 the worker was covered only indirectly (precache list served,
``CACHE_VERSION`` fresh). These tests run the real ``sw.js`` in Node through
``js/sw_harness.js`` — a fake ServiceWorkerGlobalScope with an in-memory
CacheStorage and a scripted network — and pin the contract written in the
worker's header comment:

* install precaches every ``PRECACHE_URLS`` entry with ``cache: 'reload'``,
  tolerates a missing optional asset, but FAILS when the shell itself cannot
  be cached (no silent "offline mode" that has nothing to serve);
* activate deletes every cache except the current build and claims clients;
* the worker never touches non-GET requests, cross-origin requests or the
  live engine (``/v1/*``, ``/v2/*`` — even navigations to them);
* navigations are network-first with the cached shell as offline fallback
  (503 text when nothing is cached); a 5xx from the server is passed through
  and does not overwrite the good cached copy;
* other same-origin GETs are stale-while-revalidate; error statuses are never
  cached; offline without a copy is a 504 text, never a fake 200.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SW_PATH = PROJECT_ROOT / "sw.js"
HARNESS = Path(__file__).with_name("js") / "sw_harness.js"


@pytest.fixture(scope="module")
def sw() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable for the service-worker harness")
    completed = subprocess.run(
        [node, str(HARNESS), str(SW_PATH)], capture_output=True, text=True, check=False, timeout=120
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    broken = {k: v["harnessError"] for k, v in result.items() if "harnessError" in v}
    assert not broken, broken
    return result


def test_install_precaches_every_listed_asset_with_cache_reload(sw: dict) -> None:
    s = sw["install_precaches_everything"]
    assert s["cacheName"] == f"antibio-shell-{s['cacheVersion']}"
    assert s["cacheVersion"].startswith("build-")
    assert s["cachedUrls"] == sorted(s["precacheUrls"])
    assert s["shellCached"] is True
    assert s["skipWaiting"] == 1
    # `cache: 'reload'` bypasses the HTTP cache so a new build is really fetched
    assert s["requestCacheModes"] == ["reload"]


def test_install_tolerates_a_missing_optional_asset(sw: dict) -> None:
    s = sw["install_survives_a_missing_optional_asset"]
    assert s["error"] is None
    assert s["shellCached"] is True
    assert s["missingCached"] is False
    assert s["cachedCount"] == len(sw["install_precaches_everything"]["precacheUrls"]) - 1
    assert s["skipWaiting"] == 1


def test_install_fails_when_the_shell_cannot_be_cached(sw: dict) -> None:
    s = sw["install_fails_without_the_shell"]
    assert s["error"] and "app shell failed to precache" in s["error"]
    assert s["skipWaiting"] == 0, "a worker without a shell must not take over the page"


def test_activate_removes_every_other_cache_and_claims_clients(sw: dict) -> None:
    s = sw["activate_deletes_every_other_cache"]
    assert s["remaining"] == [sw["install_precaches_everything"]["cacheName"]]
    assert s["claim"] == 1


def test_fetch_routing_never_touches_engine_writes_or_third_parties(sw: dict) -> None:
    r = sw["fetch_routing"]
    not_intercepted = [
        "post_same_origin",
        "put_engine",
        "cross_origin_get",
        "engine_v1",
        "engine_v1_exact",
        "engine_v2_nested_query",
        "engine_navigation",
    ]
    assert {k: r[k] for k in not_intercepted} == {k: False for k in not_intercepted}
    intercepted = ["shell_navigation", "vendor_asset", "icon_asset", "lookalike_v10"]
    assert {k: r[k] for k in intercepted} == {k: True for k in intercepted}


def test_navigation_online_is_network_first_and_refreshes_the_shell_copy(sw: dict) -> None:
    s = sw["navigation_online_refreshes_the_cached_shell"]
    assert s["result"]["status"] == 200
    assert s["result"]["body"] == "shell-v2"
    assert s["result"]["fromCache"] is False
    assert s["cachedShell"] == "shell-v2"


def test_navigation_server_error_is_passed_through_without_poisoning_the_cache(sw: dict) -> None:
    s = sw["navigation_server_error_is_passed_through_and_not_cached"]
    assert s["result"]["status"] == 500
    assert s["cachedShell"] == "shell-v1"


def test_navigation_offline_falls_back_to_the_cached_shell(sw: dict) -> None:
    s = sw["navigation_offline_serves_the_cached_shell"]
    assert s["result"]["status"] == 200
    assert s["result"]["body"] == "shell-v1"
    assert s["result"]["fromCache"] is True


def test_navigation_offline_without_a_copy_is_an_honest_503(sw: dict) -> None:
    s = sw["navigation_offline_without_cache_is_503"]
    assert s["result"]["status"] == 503
    assert s["result"]["contentType"].startswith("text/plain")
    assert "not cached yet" in s["result"]["body"]


def test_assets_are_stale_while_revalidate(sw: dict) -> None:
    s = sw["asset_stale_while_revalidate"]
    assert s["result"]["body"] == "css-v1" and s["result"]["fromCache"] is True
    assert s["before"] == "css-v1"
    assert s["after"] == "css-v2", "the background revalidation must refresh the cache"


def test_uncached_asset_online_is_fetched_and_stored(sw: dict) -> None:
    s = sw["asset_uncached_online_is_fetched_and_cached"]
    assert s["result"]["status"] == 200 and s["result"]["fromCache"] is False
    assert s["cached"] == "font-bytes"


def test_uncached_asset_offline_is_an_honest_504(sw: dict) -> None:
    s = sw["asset_uncached_offline_is_504"]
    assert s["result"]["status"] == 504
    assert s["result"]["contentType"].startswith("text/plain")


def test_error_responses_are_never_cached(sw: dict) -> None:
    s = sw["asset_error_status_is_not_cached"]
    assert s["result"]["status"] == 404
    assert s["cachedCount"] == 0
