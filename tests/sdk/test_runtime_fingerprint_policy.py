import types
import pytest

from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.node import StreamInput
from qmtl.runtime.sdk.strategy import Strategy
from qmtl.runtime.sdk import snapshot as snap


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
    # Directly call the internal helper to avoid network/history work
    count = Runner._hydrate_snapshots(strategy)
    assert count == 0
    # Ensure we passed strict=True based on node.runtime_compat
    assert calls and calls[-1] is True
