from __future__ import annotations

import pytest

from qmtl.sdk.node import StreamInput
from qmtl.sdk.runner import Runner
from qmtl.sdk.strategy import Strategy
from qmtl.sdk.strategy_bootstrapper import BootstrapResult, StrategyBootstrapper


class CountingStreamInput(StreamInput):
    def __init__(self) -> None:
        super().__init__(interval="60s", period=1)
        self.apply_calls: int = 0
        self.seen_contexts: list[object] = []

    def apply_compute_context(self, context) -> None:  # type: ignore[override]
        self.apply_calls += 1
        self.seen_contexts.append(context)
        super().apply_compute_context(context)


class CountingStrategy(Strategy):
    def setup(self) -> None:
        node = CountingStreamInput()
        self.add_nodes([node])


@pytest.mark.asyncio
@pytest.mark.parametrize("offline", [False, True])
async def test_runner_applies_context_once(monkeypatch, offline: bool) -> None:
    before_counts: list[list[int]] = []
    after_counts: list[list[int]] = []
    received_offline: list[bool] = []

    async def fake_bootstrap(
        self,
        strategy: Strategy,
        *,
        context,
        schema_enforcement: str,
        offline: bool,
        **kwargs,
    ) -> BootstrapResult:
        received_offline.append(offline)
        before_counts.append([node.apply_calls for node in strategy.nodes])
        for node in strategy.nodes:
            setattr(node, "_schema_enforcement", schema_enforcement)
            node.apply_compute_context(context)
        after_counts.append([node.apply_calls for node in strategy.nodes])
        return BootstrapResult(
            manager=object(),
            offline_mode=offline,
            completed=True,
            dataset_fingerprint=None,
            tag_service=object(),
            dag_meta=None,
        )

    monkeypatch.setattr(StrategyBootstrapper, "bootstrap", fake_bootstrap, raising=False)

    strategy = await Runner.run_async(
        CountingStrategy,
        world_id="world",
        offline=offline,
        schema_enforcement="strict",
    )

    assert before_counts == [[0]]
    assert after_counts == [[1]]
    assert received_offline == [offline]

    node = strategy.nodes[0]
    assert isinstance(node, CountingStreamInput)
    assert node.apply_calls == 1
    assert getattr(node, "_schema_enforcement") == "strict"
    assert len(node.seen_contexts) == 1

