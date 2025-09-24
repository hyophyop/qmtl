import httpx

from qmtl.runtime.sdk import Runner, Strategy, StreamInput, ProcessingNode


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
            src = StreamInput(interval="60s", period=2)
            self.src = src

            def n1_fn(view):
                calls.append("n1")
                return view[src][60].latest()[1]["v"] + 1

            n1 = ProcessingNode(input=src, compute_fn=n1_fn, name="n1", interval="60s", period=1)

            def n2_fn(view):
                calls.append("n2")
                val = view[n1][60].latest()[1]
                out = val * 2
                results.append(out)
                return out

            n2 = ProcessingNode(input=n1, compute_fn=n2_fn, name="n2", interval="60s", period=1)

            self.add_nodes([src, n1, n2])

    return Strat


def test_run_offline_pipeline(monkeypatch):
    _mock_gateway(monkeypatch)

    class DummyFactory:
        available = True

        @staticmethod
        def create_consumer(*args, **kwargs):
            class DummyConsumer:
                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def getmany(self, timeout_ms=None):
                    return {}

            return DummyConsumer()

    monkeypatch.setattr(Runner.services(), "kafka_factory", DummyFactory())
    calls, results = [], []

    strat = Runner.offline(_make_strategy(calls, results))
    src = strat.src
    src.cache.backfill_bulk(src.node_id, 60, [(60, {"v": 1}), (120, {"v": 2})])
    Runner.run_pipeline(strat)

    assert calls == ["n1", "n2", "n1", "n2"]
    assert results == [4, 6]


def test_run_no_kafka_pipeline(monkeypatch):
    _mock_gateway(monkeypatch)

    class NoKafkaFactory:
        available = False

        @staticmethod
        def create_consumer(*args, **kwargs):
            raise RuntimeError("no kafka")

    monkeypatch.setattr(Runner.services(), "kafka_factory", NoKafkaFactory())
    calls, results = [], []

    strat = Runner.run(
        _make_strategy(calls, results), world_id="w", gateway_url="http://gw"
    )
    src = strat.src
    src.cache.backfill_bulk(src.node_id, 60, [(60, {"v": 1}), (120, {"v": 2})])
    Runner.run_pipeline(strat)

    assert calls == ["n1", "n2", "n1", "n2"]
    assert results == [4, 6]
