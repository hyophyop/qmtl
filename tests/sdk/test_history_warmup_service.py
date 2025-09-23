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
