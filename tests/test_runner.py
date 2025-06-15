import sys
import base64
import json

import httpx
import pytest
from qmtl.sdk.runner import Runner
from qmtl.sdk.node import StreamInput
from tests.sample_strategy import SampleStrategy


def test_backtest(capsys, monkeypatch):
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

    strategy = Runner.backtest(
        SampleStrategy,
        start_time="s",
        end_time="e",
        gateway_url="http://gw",
    )
    captured = capsys.readouterr().out
    assert "[BACKTEST] SampleStrategy" in captured
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


def test_dryrun(capsys, monkeypatch):
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

    strategy = Runner.dryrun(SampleStrategy, gateway_url="http://gw")
    captured = capsys.readouterr().out
    assert "[DRYRUN] SampleStrategy" in captured
    assert isinstance(strategy, SampleStrategy)


def test_live(capsys, monkeypatch):
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

    strategy = Runner.live(SampleStrategy, gateway_url="http://gw")
    captured = capsys.readouterr().out
    assert "[LIVE] SampleStrategy" in captured
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
    assert first_node.queue_topic == "topic1"
    assert not first_node.execute


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
    assert all(n.queue_topic is None for n in strategy.nodes)


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
    from qmtl.sdk import Node, StreamInput

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

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=compute, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "q", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "q", 60, 120, {"v": 2})

    assert len(dummy_ray.calls) == 1
    assert not calls


def test_feed_queue_data_without_ray(monkeypatch):
    from qmtl.sdk import Node, StreamInput

    monkeypatch.setattr(Runner, "_ray_available", False)

    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=compute, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "q", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "q", 60, 120, {"v": 2})

    assert len(calls) == 1


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

    async def dummy_load_history(self):
        called.append(self)

    monkeypatch.setattr(StreamInput, "load_history", dummy_load_history)

    Runner.dryrun(
        SampleStrategy,
        gateway_url="http://gw",
    )

    assert len(called) == 1


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

    async def dummy_load_history(self):
        called.append(self)

    monkeypatch.setattr(StreamInput, "load_history", dummy_load_history)

    argv = [
        "qmtl.sdk",
        "tests.sample_strategy:SampleStrategy",
        "--mode",
        "dryrun",
        "--gateway-url",
        "http://gw",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert len(called) == 1
