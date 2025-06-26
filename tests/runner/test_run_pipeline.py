import httpx

from qmtl.sdk import Runner, Strategy, StreamInput, ProcessingNode


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


def _make_strategy(calls, results):
    class Strat(Strategy):
        def setup(self):
            src = StreamInput(interval=60, period=2)
            src.cache.backfill_bulk(src.node_id, 60, [(60, {"v": 1}), (120, {"v": 2})])

            def n1_fn(view):
                calls.append("n1")
                return view[src][60].latest()[1]["v"] + 1

            n1 = ProcessingNode(input=src, compute_fn=n1_fn, name="n1", interval=60, period=1)

            def n2_fn(view):
                calls.append("n2")
                val = view[n1][60].latest()[1]
                out = val * 2
                results.append(out)
                return out

            n2 = ProcessingNode(input=n1, compute_fn=n2_fn, name="n2", interval=60, period=1)

            self.add_nodes([src, n1, n2])

    return Strat


def test_dryrun_offline_pipeline(monkeypatch):
    _mock_gateway(monkeypatch)
    monkeypatch.setattr(Runner, "_kafka_available", True)
    calls, results = [], []

    Runner.dryrun(_make_strategy(calls, results), gateway_url="http://gw", offline=True)

    assert calls == ["n1", "n2", "n1", "n2"]
    assert results == [4, 6]


def test_live_no_kafka_pipeline(monkeypatch):
    _mock_gateway(monkeypatch)
    monkeypatch.setattr(Runner, "_kafka_available", False)
    calls, results = [], []

    Runner.live(_make_strategy(calls, results), gateway_url="http://gw")

    assert calls == ["n1", "n2", "n1", "n2"]
    assert results == [4, 6]

