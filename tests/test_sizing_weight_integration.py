import pytest

from qmtl.sdk.node import Node
from qmtl.sdk.runner import Runner
from qmtl.pipeline.execution_nodes import SizingNode
from qmtl.sdk.portfolio import Portfolio
from qmtl.sdk.activation_manager import ActivationManager
from qmtl.common.cloudevents import EVENT_SCHEMA_VERSION


async def _emit(am: ActivationManager, side: str, **fields) -> None:
    await am._on_message(
        {
            "event": "activation_updated",
            "data": {"side": side, "version": EVENT_SCHEMA_VERSION, **fields},
        }
    )  # type: ignore


def _weight_fn_from_am(am: ActivationManager):
    def fn(order: dict) -> float:
        side = order.get("side")
        if not side:
            qty = order.get("quantity") or order.get("value") or order.get("percent") or 0.0
            side = "BUY" if float(qty) >= 0 else "SELL"
        s = str(side).upper()
        return am.weight_for_side("long" if s == "BUY" else "short")

    return fn


@pytest.mark.asyncio
async def test_sizing_applies_weight_long():
    src = Node(name="src", interval=1, period=1)
    portfolio = Portfolio(cash=1000)
    am = ActivationManager()
    await _emit(am, "long", active=True, weight=0.5)
    assert am.weight_for_side("long") == 0.5
    node = SizingNode(src, portfolio=portfolio, weight_fn=_weight_fn_from_am(am))
    order = {"symbol": "AAPL", "price": 10.0, "value": 100.0, "side": "BUY"}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["quantity"] == 5.0


@pytest.mark.asyncio
async def test_sizing_applies_weight_short():
    src = Node(name="src", interval=1, period=1)
    portfolio = Portfolio(cash=1000)
    am = ActivationManager()
    await _emit(am, "short", active=True, weight=0.2)
    node = SizingNode(src, portfolio=portfolio, weight_fn=_weight_fn_from_am(am))
    order = {"symbol": "AAPL", "price": 10.0, "percent": -0.1, "side": "SELL"}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["quantity"] == -2.0

