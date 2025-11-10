from __future__ import annotations

import pytest

from qmtl.runtime.pipeline.execution_nodes.sizing import (
    SizingNode as RealSizingNode,
)
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import StreamInput
from qmtl.runtime.sdk.portfolio import Portfolio
from qmtl.runtime.transforms.position_intent import (
    PositionTargetNode,
    Thresholds,
)


def test_position_target_node_provides_price_for_sizing():
    signal = StreamInput(
        tags=["signal"], interval=60, period=1, config={"stream": "signal"}
    )
    price = StreamInput(
        tags=["price"], interval=60, period=1, config={"stream": "price"}
    )
    node = PositionTargetNode(
        signal=signal,
        symbol="BTCUSDT",
        thresholds=Thresholds(long_enter=0.5, short_enter=-0.5),
        long_weight=1.0,
        short_weight=-1.0,
        hold_weight=0.0,
        to_order=True,
        price_node=price,
    )

    ts = 60
    signal_view = {signal.node_id: {signal.interval: [(ts, 0.75)]}}
    price_view = {price.node_id: {price.interval: [(ts, 100.0)]}}
    view = CacheView({**signal_view, **price_view})

    order = node._compute(view)
    assert order is not None
    assert order["price"] == pytest.approx(100.0)
    assert order["target_percent"] == pytest.approx(1.0)

    sizing = RealSizingNode(node, portfolio=Portfolio(cash=1_000.0))
    sizing_view = CacheView({node.node_id: {node.interval: [(ts, order)]}})
    sized = sizing._compute(sizing_view)

    assert sized is not None
    assert sized["price"] == pytest.approx(100.0)
    assert sized["quantity"] == pytest.approx(10.0)


def test_position_target_node_price_guard_handles_empty_stream():
    signal = StreamInput(
        tags=["signal"], interval=60, period=1, config={"stream": "signal"}
    )
    price = StreamInput(
        tags=["price"], interval=60, period=1, config={"stream": "price"}
    )
    node = PositionTargetNode(
        signal=signal,
        symbol="BTCUSDT",
        thresholds=Thresholds(long_enter=0.5, short_enter=-0.5),
        to_order=True,
        price_node=price,
    )

    ts = 60
    signal_view = {signal.node_id: {signal.interval: [(ts, 0.75)]}}
    price_view = {price.node_id: {price.interval: []}}
    view = CacheView({**signal_view, **price_view})

    with pytest.raises(ValueError) as excinfo:
        node._compute(view)

    assert "no price data available" in str(excinfo.value)
