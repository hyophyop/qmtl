from __future__ import annotations

import types

import pytest

from qmtl.runtime.sdk import Strategy, StreamInput
from qmtl.runtime.sdk.history_warmup_service import HistoryWarmupService


class SimpleStrategy(Strategy):
    def setup(self) -> None:
        node = StreamInput(interval="60s", period=1)
        self.add_nodes([node])


@pytest.mark.asyncio
async def test_history_service_prefers_auto_backfill(monkeypatch):
    class AutoProvider:
        def __init__(self) -> None:
            self.ensure_calls: list[tuple[int, int, str, int]] = []
            self.coverage_calls: list[tuple[str, int]] = []
            self._coverage: dict[tuple[str, int], list[tuple[int, int]]] = {}

        async def coverage(self, *, node_id, interval):
            self.coverage_calls.append((node_id, interval))
            return list(self._coverage.get((node_id, interval), []))

        async def ensure_range(self, start, end, *, node_id, interval):
            self.ensure_calls.append((start, end, node_id, interval))
            self._coverage[(node_id, interval)] = [(start, end)]

        async def fill_missing(self, start, end, *, node_id, interval):  # pragma: no cover
            raise AssertionError("fill_missing should not be invoked when ensure_range exists")

    provider = AutoProvider()
    node = StreamInput(interval=60, period=3, history_provider=provider)
    service = HistoryWarmupService()

    load_calls: list[tuple[int, int]] = []

    async def fake_load(self, start, end):
        load_calls.append((start, end))

    monkeypatch.setattr(node, "load_history", types.MethodType(fake_load, node))

    await service.ensure_node_history(node, 60, 180)

    assert provider.ensure_calls == [(60, 180, node.node_id, 60)]
    assert provider.coverage_calls
    assert load_calls == [(60, 180)]


@pytest.mark.asyncio
async def test_history_service_offline_defaults(monkeypatch):
    strategy = SimpleStrategy()
    strategy.setup()
    service = HistoryWarmupService()
    service.hydrate_snapshots = lambda s: None  # type: ignore[assignment]
    recorded: list[tuple[int | None, int | None, bool, bool]] = []
    replays: list[tuple[int | None, int | None]] = []

    async def fake_ensure(self, strat, start, end, *, stop_on_ready, strict):
        recorded.append((start, end, stop_on_ready, strict))

    async def fake_replay(self, strat, start, end, *, on_missing="skip"):
        replays.append((start, end))

    service.ensure_history = types.MethodType(fake_ensure, service)  # type: ignore[assignment]
    service.replay_history = types.MethodType(fake_replay, service)  # type: ignore[assignment]

    await service.warmup_strategy(
        strategy,
        offline_mode=True,
        history_start=None,
        history_end=None,
    )

    assert recorded == [(1, 2, True, False)]
    assert replays == []  # no provider, so no replay


@pytest.mark.asyncio
async def test_history_service_with_provider_and_strict(monkeypatch):
    class Provider:
        async def coverage(self, *, node_id, interval):
            return [(0, 60)]

        async def fill_missing(self, start, end, *, node_id, interval):
            return None

    class ProviderStrategy(Strategy):
        def setup(self) -> None:
            src = StreamInput(interval="60s", period=1, history_provider=Provider())
            src.pre_warmup = False
            self.add_nodes([src])

    strategy = ProviderStrategy()
    strategy.setup()
    node = strategy.nodes[0]

    service = HistoryWarmupService()
    service.hydrate_snapshots = lambda s: None  # type: ignore[assignment]
    monkeypatch.setattr("qmtl.runtime.sdk.runtime.FAIL_ON_HISTORY_GAP", True, raising=False)

    recorded: list[tuple[int | None, int | None, bool, bool]] = []
    replay_calls: list[tuple[int | None, int | None]] = []
    strict_calls: list[Strategy] = []

    async def fake_ensure(self, strat, start, end, *, stop_on_ready, strict):
        recorded.append((start, end, stop_on_ready, strict))

    async def fake_replay(self, strat, start, end, *, on_missing="skip"):
        replay_calls.append((start, end))

    async def fake_strict(self, strat):
        strict_calls.append(strat)

    service.ensure_history = types.MethodType(fake_ensure, service)  # type: ignore[assignment]
    service.replay_history = types.MethodType(fake_replay, service)  # type: ignore[assignment]
    service._enforce_strict_mode = types.MethodType(fake_strict, service)  # type: ignore[assignment]

    await service.warmup_strategy(
        strategy,
        offline_mode=True,
        history_start=None,
        history_end=None,
    )

    assert recorded == [(None, None, True, True)]
    assert replay_calls == [(None, None)]
    assert strict_calls == [strategy]


def test_replay_events_simple_orders_dependencies():
    class TestStream(StreamInput):
        def __init__(self, node_id_value: str, **kwargs) -> None:
            self._node_id_override = node_id_value
            super().__init__(**kwargs)

        @property
        def node_id(self) -> str:  # type: ignore[override]
            return self._node_id_override

    service = HistoryWarmupService()
    src_a = TestStream("src_a", tags=["A"], interval=60, period=3)
    src_b = TestStream("src_b", tags=["B"], interval=60, period=3)
    src_a.cache.append(src_a.node_id, src_a.interval, 60, 1)
    src_b.cache.append(src_b.node_id, src_b.interval, 60, 2)

    adder_results: list[int] = []
    aggregator_results: list[int] = []

    class AdderNode:
        def __init__(self) -> None:
            self.node_id = "adder"
            self.interval = 60
            self.inputs = [src_a, src_b]
            self.compute_fn = self._compute
            self.execute = True

        def _compute(self, view):
            left = view[src_a.node_id][src_a.interval][-1][1]
            right = view[src_b.node_id][src_b.interval][-1][1]
            result = left + right
            adder_results.append(result)
            return result

    class AggregatorNode:
        def __init__(self, upstream) -> None:
            self.node_id = "aggregator"
            self.interval = 60
            self.inputs = [upstream]
            self.compute_fn = self._compute
            self.execute = True

        def _compute(self, view):
            latest = view[adder.node_id][adder.interval][-1][1]
            doubled = latest * 2
            aggregator_results.append(doubled)
            return doubled

    adder = AdderNode()
    aggregator = AggregatorNode(adder)
    strategy = types.SimpleNamespace(nodes=[src_a, src_b, adder, aggregator])

    service.replay_events_simple(strategy)

    assert adder_results == [3]
    assert aggregator_results == [6]
