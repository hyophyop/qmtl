import httpx
import pytest
from qmtl.services.dagmanager.alerts import PagerDutyClient, SlackClient


@pytest.mark.asyncio
async def test_alert_clients(monkeypatch):
    calls = []

    class DummyClient:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def post(self, url, json=None):
            calls.append((url, json))
            return httpx.Response(202)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    pd = PagerDutyClient("http://pd")
    sl = SlackClient("http://slack")

    await pd.send("neo4j down")
    await sl.send("kafka lost")

    assert calls == [
        ("http://pd", {"text": "neo4j down"}),
        ("http://slack", {"text": "kafka lost"}),
    ]
