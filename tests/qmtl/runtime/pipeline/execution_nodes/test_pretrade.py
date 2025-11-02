from __future__ import annotations

from qmtl.runtime.brokerage.order import Account
from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.order_gate import Activation
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.watermark import WatermarkGate, clear_watermarks, set_watermark

from qmtl.runtime.pipeline.execution_nodes.pretrade import PreTradeGateNode


def _make_source(name: str = "src") -> Node:
    src = Node(name=name, interval=60, period=1)
    src.world_id = f"{name}-world"
    return src


class DummyBrokerage:
    def can_submit_order(self, account: Account, order: dict) -> bool:  # noqa: D401 - stub
        return True


def test_pretrade_allows_when_watermark_ready() -> None:
    clear_watermarks()
    src = _make_source()
    node = PreTradeGateNode(
        src,
        activation_map={"AAPL": Activation(True)},
        brokerage=DummyBrokerage(),
        account=Account(),
        watermark_gate=WatermarkGate(enabled=True),
    )
    set_watermark("trade.portfolio", src.world_id, 0)
    order = {"symbol": "AAPL", "quantity": 1, "price": 10.0}
    out = Runner.feed_queue_data(node, src.node_id, 60, 60, order)
    assert out == order


def test_pretrade_blocks_until_watermark_caught_up() -> None:
    clear_watermarks()
    src = _make_source("lag")
    node = PreTradeGateNode(
        src,
        activation_map={"AAPL": Activation(True)},
        brokerage=DummyBrokerage(),
        account=Account(),
        watermark_gate=WatermarkGate(enabled=True),
    )
    order = {"symbol": "AAPL", "quantity": 1, "price": 10.0}
    rejected = Runner.feed_queue_data(node, src.node_id, 60, 180, order)
    assert rejected == {"rejected": True, "reason": "watermark"}
    set_watermark("trade.portfolio", src.world_id, 180)
    allowed = Runner.feed_queue_data(node, src.node_id, 60, 240, order)
    assert allowed["symbol"] == "AAPL"
