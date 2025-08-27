import sys
import base64
import json
import logging

import httpx
import pandas as pd
import pytest
from qmtl.sdk.runner import Runner
from qmtl.sdk.node import StreamInput, ProcessingNode
from qmtl.sdk import Strategy
from tests.sample_strategy import SampleStrategy


def test_backtest(caplog, monkeypatch):
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

    with caplog.at_level(logging.INFO):
        strategy = Runner.backtest(
            SampleStrategy,
            start_time="s",
            end_time="e",
            gateway_url="http://gw",
        )
    messages = [r.getMessage() for r in caplog.records]
    assert any("[BACKTEST] SampleStrategy" in m for m in messages)
    assert isinstance(strategy, SampleStrategy)


def test_backtest_requires_start_and_end(monkeypatch):
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

    with pytest.raises(ValueError):
        Runner.backtest(
            SampleStrategy,
            gateway_url="http://gw",
            end_time="e",
        )

    with pytest.raises(ValueError):
        Runner.backtest(
            SampleStrategy,
            gateway_url="http://gw",
            start_time="s",
        )


def test_dry_run(caplog, monkeypatch):
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

    with caplog.at_level(logging.INFO):
        strategy = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    messages = [r.getMessage() for r in caplog.records]
    assert any("[DRYRUN] SampleStrategy" in m for m in messages)
    assert isinstance(strategy, SampleStrategy)


def test_live(caplog, monkeypatch):
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

    with caplog.at_level(logging.INFO):
        strategy = Runner.live(SampleStrategy, gateway_url="http://gw")
    messages = [r.getMessage() for r in caplog.records]
    assert any("[LIVE] SampleStrategy" in m for m in messages)
    assert isinstance(strategy, SampleStrategy)


def test_gateway_queue_mapping(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        dag = json.loads(base64.b64decode(payload["dag_json"]).decode())
        first_node = dag["nodes"][0]
        assert "code_hash" in first_node and "schema_hash" in first_node
        first_id = first_node["node_id"]
        return httpx.Response(
            202,
            json={"strategy_id": "s1", "queue_map": {first_id: "topic1"}},
        )

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

    strategy = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    first_node = strategy.nodes[0]
    assert first_node.kafka_topic == "topic1"
    assert not first_node.execute


def test_dry_run_exits_when_all_nodes_mapped(monkeypatch, caplog):
    async def fake_post_gateway_async(*, gateway_url, dag, meta, run_type, circuit_breaker):
        return {n["node_id"]: "topic" for n in dag["nodes"]}

    def fake_run_pipeline(strategy):
        raise RuntimeError("should not run")

    monkeypatch.setattr(Runner, "_post_gateway_async", staticmethod(fake_post_gateway_async))
    monkeypatch.setattr(Runner, "run_pipeline", fake_run_pipeline)

    with caplog.at_level(logging.INFO):
        strategy = Runner.dryrun(SampleStrategy, gateway_url="http://gw")

    messages = [r.getMessage() for r in caplog.records]
    assert any("No executable nodes" in m for m in messages)
    assert all(not n.execute for n in strategy.nodes)


def test_live_exits_when_all_nodes_mapped(monkeypatch, caplog):
    from qmtl.sdk.tagquery_manager import TagQueryManager

    async def fake_post_gateway_async(*, gateway_url, dag, meta, run_type, circuit_breaker):
        return {n["node_id"]: "topic" for n in dag["nodes"]}

    def fake_run_pipeline(strategy):
        raise RuntimeError("should not run")

    async def fake_start(self):
        raise RuntimeError("should not start")

    monkeypatch.setattr(Runner, "_post_gateway_async", staticmethod(fake_post_gateway_async))
    monkeypatch.setattr(Runner, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(TagQueryManager, "start", fake_start)

    with caplog.at_level(logging.INFO):
        strategy = Runner.live(SampleStrategy, gateway_url="http://gw")

    messages = [r.getMessage() for r in caplog.records]
    assert any("No executable nodes" in m for m in messages)
    assert all(not n.execute for n in strategy.nodes)


def test_gateway_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409)

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

    with pytest.raises(RuntimeError):
        Runner.dryrun(SampleStrategy, gateway_url="http://gw")


def test_offline_mode():
    strategy = Runner.offline(SampleStrategy)
    assert all(n.execute for n in strategy.nodes)
    assert all(n.kafka_topic is None for n in strategy.nodes)


def test_connection_failure(monkeypatch):
    class DummyClient:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def post(self, url, json=None):
            raise httpx.RequestError("fail", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    with pytest.raises(RuntimeError):
        Runner.dryrun(SampleStrategy, gateway_url="http://gw")


def test_offline_same_ids(monkeypatch):
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

    online = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    offline = Runner.offline(SampleStrategy)
    assert [n.node_id for n in online.nodes] == [n.node_id for n in offline.nodes]


def test_no_gateway_same_ids(monkeypatch):
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

    online = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    with pytest.raises(RuntimeError):
        Runner.dryrun(SampleStrategy)


def test_feed_queue_data_with_ray(monkeypatch):
    from qmtl.sdk import ProcessingNode, StreamInput

    class DummyRay:
        def __init__(self):
            self.calls = []
            self.inited = False

        def is_initialized(self):
            return self.inited

        def init(self, ignore_reinit_error=True):
            self.inited = True

        def remote(self, fn):
            dummy = self

            class Wrapper:
                def remote(self, *args, **kwargs):
                    dummy.calls.append((fn, args, kwargs))

            return Wrapper()

    dummy_ray = DummyRay()
    import qmtl.sdk.runner as rmod

    monkeypatch.setattr(rmod, "ray", dummy_ray)
    monkeypatch.setattr(rmod.Runner, "_ray_available", True)

    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n", interval="60s", period=2)

    Runner.feed_queue_data(node, "q", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "q", 60, 120, {"v": 2})

    assert len(dummy_ray.calls) == 1
    assert not calls


def test_feed_queue_data_without_ray(monkeypatch):
    from qmtl.sdk import ProcessingNode, StreamInput

    monkeypatch.setattr(Runner, "_ray_available", False)

    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n", interval="60s", period=2)

    Runner.feed_queue_data(node, "q", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "q", 60, 120, {"v": 2})

    assert len(calls) == 1


def test_feed_queue_data_respects_execute_flag(monkeypatch):
    from qmtl.sdk import ProcessingNode, StreamInput

    monkeypatch.setattr(Runner, "_ray_available", False)

    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n", interval="60s", period=2)
    node.execute = False

    Runner.feed_queue_data(node, "q", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "q", 60, 120, {"v": 2})

    assert not calls


def test_load_history_called(monkeypatch):
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

    called = []

    async def dummy_load_history(self, start, end):
        called.append((start, end))

    monkeypatch.setattr(StreamInput, "load_history", dummy_load_history)

    Runner.backtest(
        SampleStrategy,
        start_time=1,
        end_time=2,
        gateway_url="http://gw",
    )

    assert called == [(1, 2)]


def test_cli_execution(monkeypatch):
    import sys
    from qmtl.sdk.cli import main

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

    called = []

    async def dummy_load_history(self, start, end):
        called.append((start, end))

    monkeypatch.setattr(StreamInput, "load_history", dummy_load_history)

    argv = [
        "qmtl.sdk",
        "tests.sample_strategy:SampleStrategy",
        "--mode",
        "backtest",
        "--start-time",
        "1",
        "--end-time",
        "2",
        "--gateway-url",
        "http://gw",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert called == [("1", "2")]


def test_history_gap_fill(monkeypatch):
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

    coverage_calls = []
    fill_calls = []

    class DummyProvider:
        def __init__(self):
            self.ranges = []

        async def fetch(self, start, end, *, node_id, interval):
            return None

        async def coverage(self, *, node_id, interval):
            coverage_calls.append((node_id, interval))
            return list(self.ranges)

        async def fill_missing(self, start, end, *, node_id, interval):
            fill_calls.append((start, end, node_id, interval))
            self.ranges.append((start, end))

    provider = DummyProvider()

    class Strat(SampleStrategy):
        def setup(self):
            src = StreamInput(interval="1s", period=1, history_provider=provider)
            node = ProcessingNode(input=src, compute_fn=lambda df: df, name="out", interval="1s", period=1)
            self.add_nodes([src, node])

    Runner.backtest(Strat, start_time=60, end_time=120, gateway_url="http://gw")

    assert coverage_calls
    assert fill_calls


def test_history_gap_fill_stops_on_ready(monkeypatch):
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

    coverage_calls = []
    fill_calls = []
    holder = {}

    class DummyProvider:
        async def fetch(self, start, end, *, node_id, interval):
            return None

        async def coverage(self, *, node_id, interval):
            coverage_calls.append((node_id, interval))
            return []

        async def fill_missing(self, start, end, *, node_id, interval):
            fill_calls.append((start, end, node_id, interval))
            holder["src"].pre_warmup = False

    provider = DummyProvider()

    class Strat(SampleStrategy):
        def setup(self):
            src = StreamInput(interval="1s", period=1, history_provider=provider)
            holder["src"] = src
            node = ProcessingNode(input=src, compute_fn=lambda df: df, name="out", interval="1s", period=1)
            self.add_nodes([src, node])

    Runner.dryrun(Strat, gateway_url="http://gw")

    assert coverage_calls == [(holder["src"].node_id, 1)]
    assert len(fill_calls) == 1


def test_backtest_replay_history_multi_inputs(monkeypatch):
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

    calls = []

    class Strat(Strategy):
        def setup(self):
            a = StreamInput(interval="60s", period=2, history_provider=DummyProvider())
            b = StreamInput(interval="60s", period=2, history_provider=DummyProvider())

            def compute(view):
                av = view[a][60].latest()[1]["v"]
                bv = view[b][60].latest()[1]["v"]
                calls.append(av + bv)

            node = ProcessingNode(input=[a, b], compute_fn=compute, name="out", interval="60s", period=2)
            self.add_nodes([a, b, node])

    Runner.backtest(Strat, start_time=60, end_time=120, gateway_url="http://gw")

    assert calls == [4]


def test_backtest_on_missing_fail(monkeypatch):
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

    class GapProvider:
        async def fetch(self, start, end, *, node_id, interval):
            return pd.DataFrame([
                {"ts": 60, "v": 1},
                {"ts": 180, "v": 2},
            ])

        async def coverage(self, *, node_id, interval):
            return [(60, 180)]

        async def fill_missing(self, start, end, *, node_id, interval):
            pass

    class Strat(Strategy):
        def setup(self):
            src = StreamInput(interval="60s", period=2, history_provider=GapProvider())
            node = ProcessingNode(input=src, compute_fn=lambda v: v, name="n", interval="60s", period=2)
            self.add_nodes([src, node])

    with pytest.raises(RuntimeError):
        Runner.backtest(
            Strat,
            start_time=60,
            end_time=180,
            on_missing="fail",
            gateway_url="http://gw",
        )


def test_ray_flag_auto_set(monkeypatch):
    import sys
    import importlib
    import qmtl.sdk.runner as rmod

    original_ray = sys.modules.get("ray")

    # simulate absence of ray
    monkeypatch.delitem(sys.modules, "ray", raising=False)
    importlib.reload(rmod)
    assert not rmod.Runner._ray_available

    # simulate presence of ray
    class DummyModule:
        pass

    monkeypatch.setitem(sys.modules, "ray", DummyModule())
    importlib.reload(rmod)
    assert rmod.Runner._ray_available

    # restore original state
    if original_ray is None:
        monkeypatch.delitem(sys.modules, "ray", raising=False)
    else:
        monkeypatch.setitem(sys.modules, "ray", original_ray)
    importlib.reload(rmod)


def test_cli_disable_ray(monkeypatch):
    import sys
    import importlib
    import qmtl.sdk.cli as cli_mod
    import qmtl.sdk.runner as rmod
    from qmtl.sdk import runtime

    dummy_ray = object()
    monkeypatch.setattr(rmod, "ray", dummy_ray)
    monkeypatch.setattr(rmod.Runner, "_ray_available", True)
    monkeypatch.setattr(runtime, "NO_RAY", False)
    importlib.reload(cli_mod)

    argv = [
        "qmtl.sdk",
        "tests.sample_strategy:SampleStrategy",
        "--mode",
        "offline",
        "--no-ray",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    cli_mod.main()
    assert runtime.NO_RAY
