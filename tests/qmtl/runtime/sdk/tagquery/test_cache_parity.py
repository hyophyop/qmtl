import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from qmtl.foundation.config import CacheConfig, ConnectorsConfig, UnifiedConfig
from qmtl.runtime.sdk import TagQueryNode
from qmtl.runtime.sdk.configuration import runtime_config_override
from qmtl.runtime.sdk.tagquery_manager import TagQueryManager


class DummyClient:
    def __init__(self, *a, handler=None, **k):
        self._handler = handler
        self._client = httpx.Client(transport=httpx.MockTransport(handler))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._client.close()

    async def get(self, url, params=None):
        request = httpx.Request("GET", url, params=params)
        resp = self._handler(request)
        resp.request = request
        return resp


def test_offline_cache_parity(tmp_path, monkeypatch):
    async def run_case() -> None:
        node_live = TagQueryNode(["t"], interval="60s", period=1)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"queues": [{"queue": "q1", "global": False}]})

        monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyClient(handler=handler))

        cache = tmp_path / "tagcache.json"
        mgr_live = TagQueryManager("http://gw", cache_path=cache)
        mgr_live.register(node_live)
        await mgr_live.resolve_tags()
        assert node_live.upstreams == ["q1"]

        data = json.loads(cache.read_text())
        assert data["crc32"] == TagQueryManager._compute_crc(data["mappings"])

        node_off = TagQueryNode(["t"], interval="60s", period=1)
        mgr_off = TagQueryManager(cache_path=cache)
        mgr_off.register(node_off)
        await mgr_off.resolve_tags(offline=True)
        assert node_off.upstreams == ["q1"]
        assert node_off.upstreams == node_live.upstreams

    asyncio.run(run_case())


def test_backtest_default_cache_path_uses_ephemeral_namespace(monkeypatch):
    monkeypatch.setenv("WORLD_ID", "Paper World")
    cfg = UnifiedConfig(
        cache=CacheConfig(tagquery_cache_path=".qmtl_tagmap.json"),
        connectors=ConnectorsConfig(execution_domain="dryrun"),
        present_sections=frozenset({"cache", "connectors"}),
    )

    with runtime_config_override(cfg):
        manager = TagQueryManager()

    assert manager.cache_path == (
        Path(tempfile.gettempdir())
        / "qmtl"
        / "tagquery_cache"
        / "world=paper-world"
        / "execution_domain=dryrun"
        / ".qmtl_tagmap.json"
    )


def test_explicit_world_id_scopes_cache_path_even_without_env(monkeypatch):
    monkeypatch.delenv("WORLD_ID", raising=False)
    cfg = UnifiedConfig(
        cache=CacheConfig(tagquery_cache_path=".qmtl_tagmap.json"),
        connectors=ConnectorsConfig(execution_domain="backtest"),
        present_sections=frozenset({"cache", "connectors"}),
    )

    with runtime_config_override(cfg):
        manager_a = TagQueryManager(world_id="alpha world")
        manager_b = TagQueryManager(world_id="beta world")

    assert manager_a.cache_path == (
        Path(tempfile.gettempdir())
        / "qmtl"
        / "tagquery_cache"
        / "world=alpha-world"
        / "execution_domain=backtest"
        / ".qmtl_tagmap.json"
    )
    assert manager_b.cache_path == (
        Path(tempfile.gettempdir())
        / "qmtl"
        / "tagquery_cache"
        / "world=beta-world"
        / "execution_domain=backtest"
        / ".qmtl_tagmap.json"
    )
