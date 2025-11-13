from __future__ import annotations

from types import SimpleNamespace

import pytest

from qmtl.runtime.nodesets.recipes import (
    INTENT_FIRST_DEFAULT_THRESHOLDS,
    _build_intent_node,
    _create_intent_guard_node,
    _intent_pretrade_factory,
    _seed_execution_resources,
    _wrap_pretrade_gate_output,
)
from qmtl.runtime.sdk import CacheView, Node, Portfolio
from qmtl.runtime.sdk.order_gate import Activation


def _make_signal_node(name: str = "signal") -> Node:
    return Node(compute_fn=lambda view: None, name=name, interval=1, period=1)


def test_seed_execution_resources_initializes_cash() -> None:
    resources = SimpleNamespace(portfolio=Portfolio(), weight_fn=lambda order: 1.0)

    portfolio, weight_fn = _seed_execution_resources(resources, initial_cash=1_000.0)

    assert portfolio is resources.portfolio
    assert portfolio.cash == pytest.approx(1_000.0)
    assert weight_fn is resources.weight_fn


def test_build_intent_node_sets_world_and_price_resolver() -> None:
    signal = _make_signal_node()
    resolver = lambda view: 42.0

    intent = _build_intent_node(
        signal,
        symbol="BTCUSDT",
        thresholds=INTENT_FIRST_DEFAULT_THRESHOLDS,
        long_weight=1.0,
        short_weight=-1.0,
        hold_weight=0.0,
        price_node=None,
        price_resolver=resolver,
        world_id="world-123",
    )

    assert intent.world_id == "world-123"
    assert intent.price_resolver is resolver


def test_create_intent_guard_node_sizes_missing_quantity() -> None:
    signal = _make_signal_node()
    intent = _build_intent_node(
        signal,
        symbol="ETHUSDT",
        thresholds=INTENT_FIRST_DEFAULT_THRESHOLDS,
        long_weight=0.5,
        short_weight=-0.5,
        hold_weight=0.0,
        price_node=None,
        price_resolver=lambda view: 100.0,
        world_id="world-guard",
    )

    resources = SimpleNamespace(portfolio=Portfolio(), weight_fn=lambda order: 1.0)
    portfolio, weight_fn = _seed_execution_resources(resources, initial_cash=2_000.0)

    guard = _create_intent_guard_node(
        intent,
        portfolio=portfolio,
        weight_fn=weight_fn,
        world_id="world-guard",
    )

    payload = {"symbol": "ETHUSDT", "price": 100.0, "percent": 0.5}
    view = CacheView({intent.node_id: {intent.interval: [(1, payload)]}})

    sized = guard.compute_fn(view)
    assert sized is not None
    assert sized["quantity"] == pytest.approx(10.0)


def test_wrap_pretrade_gate_output_strips_quantity_and_links_nodes() -> None:
    signal = _make_signal_node()
    intent = _build_intent_node(
        signal,
        symbol="SOLUSDT",
        thresholds=INTENT_FIRST_DEFAULT_THRESHOLDS,
        long_weight=1.0,
        short_weight=-1.0,
        hold_weight=0.0,
        price_node=None,
        price_resolver=lambda view: 25.0,
        world_id="world-wrap",
    )

    guard = _create_intent_guard_node(
        intent,
        portfolio=None,
        weight_fn=None,
        world_id="world-wrap",
    )

    gate = Node(
        input=guard,
        compute_fn=lambda view: None,
        name="pretrade_gate",
        interval=intent.interval,
        period=1,
    )

    stage = _wrap_pretrade_gate_output(gate, intent=intent, guard=guard)

    assert getattr(stage, "intent_node") is intent
    assert getattr(stage, "pretrade_node") is gate
    assert getattr(stage, "_intent_guard_node") is guard

    view = CacheView({gate.node_id: {gate.interval: [(1, {"quantity": 5, "symbol": "SOLUSDT"})]}})
    sanitized = stage.compute_fn(view)
    assert sanitized == {"symbol": "SOLUSDT"}


def test_intent_pretrade_factory_uses_default_activation_map() -> None:
    signal = _make_signal_node()
    price_node = Node(compute_fn=lambda view: 25.0, name="price", interval=1, period=1)
    resources = SimpleNamespace(portfolio=Portfolio(), weight_fn=None)

    stage = _intent_pretrade_factory(
        signal,
        symbol="ADAUSDT",
        thresholds=INTENT_FIRST_DEFAULT_THRESHOLDS,
        long_weight=1.0,
        short_weight=-1.0,
        hold_weight=0.0,
        price_node=price_node,
        price_resolver=None,
        activation_map=None,
        brokerage=None,
        account=None,
        resources=resources,
        world_id="world-activation",
        initial_cash=500.0,
    )

    gate = getattr(stage, "pretrade_node")
    assert "ADAUSDT" in gate.activation_map
    assert gate.activation_map["ADAUSDT"] == Activation(enabled=True)

