import httpx
import pandas as pd
import pytest

from qmtl.runtime.sdk import ProcessingNode, StreamInput, Strategy
from qmtl.runtime.sdk import runtime
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.seamless_data_provider import SeamlessDataProvider, DataAvailabilityStrategy
from tests.sample_strategy import SampleStrategy


def test_run_requires_world_id_and_gateway():
    strategy = Runner.run(
        SampleStrategy,
        world_id="w",
        gateway_url=None,
    )
    assert isinstance(strategy, SampleStrategy)


def test_offline_mode():
    strategy = Runner.offline(SampleStrategy)
    assert all(node.execute for node in strategy.nodes)
    assert all(node.kafka_topic is None for node in strategy.nodes)


@pytest.mark.parametrize("online_first", [True, False])
def test_online_offline_node_ids_match(online_first, runner_with_gateway):
    if online_first:
        online = runner_with_gateway()
        offline = Runner.offline(SampleStrategy)
    else:
        offline = Runner.offline(SampleStrategy)
        online = runner_with_gateway()

    assert [node.node_id for node in online.nodes] == [node.node_id for node in offline.nodes]


def test_feed_queue_data_with_ray(monkeypatch):
    executor = Runner.services().ray_executor
    calls = []

    def fake_execute(fn, view):
        calls.append((fn, view))
        return None

    monkeypatch.setattr(executor, "execute", fake_execute)

    local_calls = []

    def compute(view):
        local_calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n", interval="60s", period=2)

    Runner.feed_queue_data(node, "q", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "q", 60, 120, {"v": 2})

    assert len(calls) == 1
    assert not local_calls


def test_feed_queue_data_without_ray(monkeypatch):
    executor = Runner.services().ray_executor
    monkeypatch.setattr(executor, "execute", lambda fn, view: fn(view))

    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n", interval="60s", period=2)

    Runner.feed_queue_data(node, "q", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "q", 60, 120, {"v": 2})

    assert len(calls) == 1


def test_feed_queue_data_respects_execute_flag(monkeypatch):
    executor = Runner.services().ray_executor
    monkeypatch.setattr(executor, "execute", lambda fn, view: fn(view))

    calls = []

    def compute(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=compute, name="n", interval="60s", period=2)
    node.execute = False

    Runner.feed_queue_data(node, "q", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "q", 60, 120, {"v": 2})

    assert not calls


def test_load_history_called(monkeypatch, runner_with_gateway):
    calls = []

    async def dummy_load_history(self, start, end):
        calls.append((start, end))

    monkeypatch.setattr(StreamInput, "load_history", dummy_load_history)

    runner_with_gateway()

    assert calls == [(1, 2)]


def test_offline_history_window(monkeypatch):
    calls: list[tuple[int, int]] = []

    async def dummy_load_history(self, start, end):
        calls.append((start, end))

    monkeypatch.setattr(StreamInput, "load_history", dummy_load_history)

    class Strat(Strategy):
        def setup(self):
            src = StreamInput(interval="60s", period=2)

            def compute(view):
                return view[src][60].latest()[1]

            node = ProcessingNode(
                input=src,
                compute_fn=compute,
                name="out",
                interval="60s",
                period=2,
            )
            self.add_nodes([src, node])

    Runner.offline(Strat, history_start=10, history_end=100)

    assert calls == [(10, 100)]


class _OfflineSeamlessProvider(SeamlessDataProvider):
    """Minimal Seamless provider for offline data binding tests."""

    def __init__(self) -> None:
        super().__init__(strategy=DataAvailabilityStrategy.FAIL_FAST)
        self.coverage_calls: list[tuple[str, int]] = []
        self.fetch_calls: list[tuple[int, int, str, int]] = []

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        self.coverage_calls.append((node_id, interval))
        # Claim broad coverage so warm-up does not attempt backfill.
        return [(0, 10_000_000_000)]

    async def fetch(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        **kwargs,
    ) -> pd.DataFrame:
        self.fetch_calls.append((start, end, node_id, interval))
        # Return an empty frame; the cache machinery only cares that the call succeeds.
        return pd.DataFrame(columns=["ts"])


@pytest.mark.asyncio
async def test_offline_binds_seamless_provider(monkeypatch):
    provider = _OfflineSeamlessProvider()

    class Strat(Strategy):
        def setup(self):
            self.src = StreamInput(interval="60s", period=2)

            def compute(view):
                # No-op compute; history warm-up is exercised via the cache path.
                return None

            node = ProcessingNode(
                input=self.src,
                compute_fn=compute,
                name="out",
                interval="60s",
                period=2,
            )
            self.add_nodes([self.src, node])

    strategy = await Runner.offline_async(
        Strat,
        history_start=10,
        history_end=70,
        data=provider,
    )

    assert provider.coverage_calls
    assert provider.fetch_calls
    assert getattr(strategy, "src").history_provider is provider


def test_history_gap_fill(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *args, **kwargs):
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

    Runner.offline(Strat)

    assert coverage_calls
    assert fill_calls


def test_history_gap_fill_with_auto_strategy(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *args, **kwargs):
            self._client = httpx.Client(transport=transport)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._client.close()

        async def post(self, url, json=None):
            request = httpx.Request("POST", url, json=json)
            return handler(request)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    coverage_calls: list[tuple[str, int]] = []

    class AutoProvider:
        def __init__(self) -> None:
            self.ensure_calls: list[tuple[int, int, str, int]] = []
            self.fetch_calls: list[tuple[int, int, str, int]] = []
            self._coverage: dict[tuple[str, int], list[tuple[int, int]]] = {}
            self._rows: dict[tuple[str, int], dict[int, dict]] = {}

        async def ensure_range(self, start, end, *, node_id, interval):
            self.ensure_calls.append((start, end, node_id, interval))
            table = self._rows.setdefault((node_id, interval), {})
            ts = start
            while ts <= end:
                table.setdefault(ts, {"value": ts})
                ts += interval
            self._coverage[(node_id, interval)] = [(start, end)]

        async def coverage(self, *, node_id, interval):
            coverage_calls.append((node_id, interval))
            return list(self._coverage.get((node_id, interval), []))

        async def fetch(self, start, end, *, node_id, interval):
            self.fetch_calls.append((start, end, node_id, interval))
            table = self._rows.get((node_id, interval), {})
            rows = []
            for ts in sorted(table):
                if start <= ts < end:
                    payload = {"ts": ts}
                    payload.update(table[ts])
                    rows.append(payload)
            return pd.DataFrame(rows)

        async def fill_missing(self, start, end, *, node_id, interval):  # pragma: no cover
            raise AssertionError("fill_missing should not be called when ensure_range exists")

    provider = AutoProvider()

    class Strat(SampleStrategy):
        def setup(self):
            src = StreamInput(interval="1s", period=3, history_provider=provider)
            node = ProcessingNode(
                input=src,
                compute_fn=lambda df: df,
                name="out",
                interval="1s",
                period=3,
            )
            self.add_nodes([src, node])

    Runner.offline(Strat)

    assert provider.ensure_calls
    assert provider.fetch_calls
    assert coverage_calls


def test_history_gap_fill_stops_on_ready(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *args, **kwargs):
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

    Runner.offline(Strat)

    assert coverage_calls
    expected = (holder["src"].node_id, 1)
    assert coverage_calls[0] == expected
    assert len(coverage_calls) <= 2
    assert len(fill_calls) == 1


def test_backtest_replay_history_multi_inputs():
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

    Runner.offline(Strat)

    assert calls == [4]


def test_backtest_on_missing_fail(monkeypatch, gateway_mock):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    gateway_mock(handler)

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

    monkeypatch.setattr(runtime, "FAIL_ON_HISTORY_GAP", True)

    with pytest.raises(RuntimeError):
        Runner.run(Strat, world_id="w", gateway_url="http://gw")
