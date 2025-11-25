import types
import pytest

from qmtl.runtime.sdk import snapshot as snap
from qmtl.runtime.sdk.history_snapshot import hydrate_strategy_snapshots
from qmtl.runtime.sdk.node import StreamInput
from qmtl.runtime.sdk.strategy import Strategy


class _S(Strategy):
    def setup(self) -> None:
        self.n = StreamInput(tags=["t"], interval=60, period=2, runtime_compat="strict")
        self.add_nodes([self.n])


def test_runner_hydrate_uses_strict_for_node_runtime_policy(monkeypatch):
    calls: list[bool] = []

    def fake_hydrate(node, *, strict_runtime=None):
        calls.append(bool(strict_runtime))
        return False

    monkeypatch.setattr(snap, "hydrate", fake_hydrate)
    strategy = _S()
    strategy.setup()
    # Call snapshot hydration helper directly to avoid network/history work
    count = hydrate_strategy_snapshots(strategy)
    assert count == 0
    # Ensure we passed strict=True based on node.runtime_compat
    assert calls and calls[-1] is True
