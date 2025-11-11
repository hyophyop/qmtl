import pytest

from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.recipes import (
    INTENT_FIRST_DEFAULT_THRESHOLDS,
    make_intent_first_nodeset,
)
from qmtl.runtime.nodesets.resources import clear_shared_portfolios
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import StreamInput


def test_intent_first_nodeset_simulate_flow():
    clear_shared_portfolios()
    signal = StreamInput(tags=["alpha"], interval=60, period=1, config={"stream": "signal"})
    price = StreamInput(tags=["price"], interval=60, period=1, config={"stream": "price"})

    nodeset = make_intent_first_nodeset(
        signal,
        "demo-world",
        symbol="BTCUSDT",
        price_node=price,
        thresholds=INTENT_FIRST_DEFAULT_THRESHOLDS,
        long_weight=0.25,
        short_weight=-0.1,
        initial_cash=50_000.0,
        options=NodeSetOptions(portfolio_scope="strategy"),
    )

    nodes = list(nodeset)
    assert nodeset.name == "intent_first"
    assert len(nodes) == 8

    pretrade = nodes[0]
    sizing = nodes[1]
    execution = nodes[2]
    publish = nodes[3]

    ts = 60
    signal_view = {signal.node_id: {signal.interval: [(ts, 0.9)]}}
    price_view = {price.node_id: {price.interval: [(ts, 100.0)]}}
    intent_view = CacheView({**signal_view, **price_view})

    intent_node = getattr(pretrade, "intent_node")
    guard = getattr(pretrade, "_intent_guard_node")
    gate = getattr(pretrade, "pretrade_node")
    order_intent = intent_node.compute_fn(intent_view)
    assert order_intent is not None
    assert pytest.approx(order_intent["target_percent"], rel=1e-3) == 0.25

    guard_view = CacheView({intent_node.node_id: {intent_node.interval: [(ts, order_intent)]}})
    guarded = guard.compute_fn(guard_view)
    assert guarded is not None
    assert guarded["quantity"] == pytest.approx(0.0)

    gate_view = CacheView({guard.node_id: {guard.interval: [(ts, guarded)]}})
    gated_raw = gate.compute_fn(gate_view)
    assert gated_raw is not None
    assert not gated_raw.get("rejected", False)

    pretrade_view = CacheView({gate.node_id: {gate.interval: [(ts, gated_raw)]}})
    gated = pretrade.compute_fn(pretrade_view)
    assert gated is not None
    assert "quantity" not in gated

    sizing_view = CacheView({pretrade.node_id: {pretrade.interval: [(ts, gated)]}})
    sized = sizing.compute_fn(sizing_view)
    assert sized is not None
    assert sized["quantity"] > 0

    execution_view = CacheView({sizing.node_id: {sizing.interval: [(ts, sized)]}})
    executed = execution.compute_fn(execution_view)
    assert executed is not None
    assert executed["quantity"] == pytest.approx(sized["quantity"])

    publish_view = CacheView({execution.node_id: {execution.interval: [(ts, executed)]}})
    published = publish.compute_fn(publish_view)
    assert published == executed
