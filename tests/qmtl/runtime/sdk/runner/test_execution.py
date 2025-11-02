import httpx
import pandas as pd
import pytest

from qmtl.runtime.sdk import Runner, Strategy, StreamInput, Node

class DummyProvider:
    async def fetch(self, start, end, *, node_id, interval):
        return pd.DataFrame([
            {"ts": 60, "v": 1},
            {"ts": 120, "v": 2},
        ])

    async def coverage(self, *, node_id, interval):
        return [(60, 120)]

    async def fill_missing(self, start, end, *, node_id, interval):
        pass


def _mock_gateway(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = httpx.Client(transport=transport)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._client.close()

        async def post(self, url, json=None):
            request = httpx.Request("POST", url, json=json)
            return handler(request)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)


def test_run_executes_nodes_offline(monkeypatch):
    _mock_gateway(monkeypatch)
    calls = []

    class Strat(Strategy):
        def setup(self):
            src = StreamInput(interval="60s", period=2, history_provider=DummyProvider())
            node = Node(input=src, compute_fn=lambda v: calls.append(v), interval="60s", period=2)
            self.add_nodes([src, node])

    Runner.offline(Strat)
    assert len(calls) == 1


def test_offline_executes_nodes():
    class Strat(Strategy):
        def setup(self):
            src = StreamInput(interval="60s", period=2)
            node = Node(input=src, compute_fn=lambda v: v, interval="60s", period=2)
            self.add_nodes([src, node])

    strategy = Runner.offline(Strat)
    assert isinstance(strategy, Strat)
