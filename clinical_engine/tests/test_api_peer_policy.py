"""Peer policy and body cap of the engine API (audit 2026-10-14, finding C-2).

`/v1/recommend` used to accept any peer and any body size while every `/v2`
route was loopback-only. The engine is loopback-only until the P6 entry gates
open, so v1 now applies the same *peer* rule (host/origin are not required for
v1 because local CLI clients use it) and both versions refuse oversized bodies
before parsing them. `server.js` forwards `X-Forwarded-For`, so a LAN request
laundered through the proxy is recognised even when the TCP peer is loopback.
"""

from __future__ import annotations

import pytest

from clinical_engine.api.service import ApiContext
from clinical_engine.corpus.locator import CorpusLocator

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from clinical_engine.api.app import create_app  # noqa: E402


def _ctx(tmp_path) -> ApiContext:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "normalized_regimens.sqlite").write_text("", encoding="utf-8")
    (root / "metadata.sqlite").write_text("", encoding="utf-8")
    return ApiContext(corpus=CorpusLocator(root), curated_knowledge_path=str(tmp_path / "k.json"))


def _client(tmp_path, peer: str | None = None) -> TestClient:
    app = create_app(_ctx(tmp_path))
    if peer is None:
        return TestClient(app, base_url="http://127.0.0.1:8000")
    return TestClient(app, base_url="http://127.0.0.1:8000", client=(peer, 54321))


_BODY = {"api_version": "1", "query": {"diagnosis": "x"}}


def test_v1_recommend_still_serves_loopback_peers(tmp_path):
    response = _client(tmp_path).post("/v1/recommend", json=_BODY)
    assert response.status_code == 200
    assert response.json()["status"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("peer", ["192.168.1.20", "10.0.0.7", "2001:db8::5"])
def test_v1_recommend_refuses_non_loopback_peers(tmp_path, peer):
    response = _client(tmp_path, peer=peer).post("/v1/recommend", json=_BODY)
    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "NON_LOOPBACK_REQUEST"


def test_v1_recommend_refuses_a_lan_client_laundered_through_a_loopback_proxy(tmp_path):
    client = _client(tmp_path)
    forwarded = client.post("/v1/recommend", json=_BODY, headers={"X-Forwarded-For": "192.168.1.20"})
    assert forwarded.status_code == 403
    assert forwarded.json()["errors"][0]["code"] == "NON_LOOPBACK_REQUEST"
    chained = client.post("/v1/recommend", json=_BODY, headers={"X-Forwarded-For": "127.0.0.1, 192.168.1.20"})
    assert chained.status_code == 403
    local_proxy = client.post("/v1/recommend", json=_BODY, headers={"X-Forwarded-For": "127.0.0.1"})
    assert local_proxy.status_code == 200


def test_v2_recommend_applies_the_same_forwarded_peer_rule(tmp_path):
    client = _client(tmp_path)
    response = client.post("/v2/recommend", json={"api_version": "2", "query": {"diagnosis": "x"}},
                           headers={"X-Forwarded-For": "192.168.1.20"})
    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "NON_LOOPBACK_REQUEST"


def test_oversized_bodies_are_refused_before_parsing(tmp_path):
    client = _client(tmp_path)
    big = {"api_version": "1", "query": {"diagnosis": "x" * (1024 * 1024 + 10)}}
    v1 = client.post("/v1/recommend", json=big)
    assert v1.status_code == 413
    assert v1.json()["errors"][0]["code"] == "PAYLOAD_TOO_LARGE"
    v2 = client.post("/v2/recommend", json={"api_version": "2", "query": {"diagnosis": "x" * (1024 * 1024 + 10)}})
    assert v2.status_code == 413
    assert v2.json()["errors"][0]["code"] == "PAYLOAD_TOO_LARGE"


def test_health_and_version_remain_open_to_any_peer(tmp_path):
    client = _client(tmp_path, peer="192.168.1.20")
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/version").status_code == 200
