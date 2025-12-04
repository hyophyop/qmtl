import pytest

from qmtl.runtime.sdk import TagQueryNode, MatchMode
from qmtl.runtime.sdk import metrics as sdk_metrics
from qmtl.runtime.sdk.tagquery_manager import TagQueryManager


@pytest.mark.asyncio
async def test_resolve_tags_normalizes_and_filters(monkeypatch):
    calls = []

    class DummyClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def get(self, url, params=None):
            calls.append((url, dict(params or {})))

            class Resp:
                status_code = 200

                def raise_for_status(self):
                    return None

                def json(self):
                    # All entries are descriptor objects; global=True must be filtered
                    return {
                        "queues": [
                            {"queue": "q1", "global": False},
                            {"queue": "q2", "global": False},
                            {"queue": "q3", "global": True},
                        ]
                    }

            return Resp()

    monkeypatch.setattr("qmtl.runtime.sdk.tagquery_manager.httpx.AsyncClient", DummyClient)

    node = TagQueryNode(["t1"], interval="60s", period=1, match_mode=MatchMode.ALL)
    mgr = TagQueryManager("http://gw", world_id="worldX")
    mgr.register(node)

    await mgr.resolve_tags(offline=False)

    # global=True entry is filtered, remaining are preserved and execute flag is set
    assert sorted(node.upstreams) == ["q1", "q2"]
    assert node.execute

    # Verify request parameters were normalized correctly
    assert calls, "no HTTP call captured"
    url, params = calls[-1]
    assert url.endswith("/queues/by_tag")
    assert params.get("tags") == "t1"
    assert params.get("interval") == 60
    assert params.get("match_mode") == "all"
    assert params.get("world_id") == "worldX"


@pytest.mark.asyncio
async def test_resolve_tags_offline_initializes_empty():
    node = TagQueryNode(["t"], interval="60s", period=1)
    mgr = TagQueryManager(None)
    mgr.register(node)
    await mgr.resolve_tags(offline=True)
    assert node.upstreams == []
    assert not node.execute


@pytest.mark.asyncio
async def test_queue_update_canonicalizes_tags_and_records_metrics():
    sdk_metrics.reset_metrics()
    node = TagQueryNode(["t2", "t1"], interval="60s", period=1)
    mgr = TagQueryManager("http://gw")
    mgr.register(node)

    await mgr._handle_queue_update(
        {
            "tags": ["t1", "t2", "t2"],
            "interval": "60",
            "match_mode": "ANY",
            "queues": [{"queue": "q1", "global": False}],
        }
    )

    assert node.upstreams == ["q1"]
    assert (
        sdk_metrics.tagquery_update_total.labels(outcome="applied", reason="ok")._value.get() == 1
    )


@pytest.mark.asyncio
async def test_queue_update_missing_interval_is_dropped():
    sdk_metrics.reset_metrics()
    node = TagQueryNode(["t"], interval="60s", period=1)
    mgr = TagQueryManager("http://gw")
    mgr.register(node)

    await mgr._handle_queue_update(
        {
            "tags": ["t"],
            "queues": [{"queue": "q1"}],
        }
    )

    assert node.upstreams == []
    assert (
        sdk_metrics.tagquery_update_total.labels(
            outcome="dropped", reason="missing_interval"
        )._value.get()
        == 1
    )
