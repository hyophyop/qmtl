from __future__ import annotations

import pytest

from qmtl.services.gateway.instrument_constraints import (
    ConstraintRule,
    InstrumentConstraints,
    ConstraintViolationError,
)
from qmtl.services.gateway.rebalancing_executor import (
    OrderOptions,
    VenuePolicy,
    orders_from_world_plan,
)
from qmtl.services.worldservice.rebalancing import RebalancePlan, SymbolDelta


def test_orders_from_world_plan_reduce_only_flag():
    plan = RebalancePlan(
        world_id="a",
        scale_world=2/3,
        scale_by_strategy={"b": 2/3},
        deltas=[
            SymbolDelta(symbol="BTCUSDT", delta_qty=-0.333, venue="binance"),
            SymbolDelta(symbol="ETHUSDT", delta_qty=0.5, venue="binance"),
        ],
    )
    orders = orders_from_world_plan(plan, options=OrderOptions(time_in_force="GTC"))
    assert len(orders) == 2
    assert orders[0]["symbol"] == "BTCUSDT"
    assert orders[0]["reduce_only"] is True
    assert orders[0]["venue"] == "binance"
    assert orders[1]["symbol"] == "ETHUSDT"
    assert "reduce_only" not in orders[1]


def test_orders_respect_lot_and_notional_filters():
    plan = RebalancePlan(
        world_id="w",
        scale_world=1.0,
        scale_by_strategy={},
        deltas=[
            SymbolDelta(symbol="BTCUSDT", delta_qty=0.0004, venue="binance"),
            SymbolDelta(symbol="ETHUSDT", delta_qty=1.5, venue="binance"),
        ],
    )
    marks = {("binance", "ETHUSDT"): 200.0}
    orders = orders_from_world_plan(
        plan,
        options=OrderOptions(
            lot_size_by_symbol={"BTCUSDT": 0.001, "ETHUSDT": 0.1},
            min_trade_notional=200.0,
            marks_by_symbol=marks,
        ),
    )
    assert len(orders) == 1
    assert orders[0]["symbol"] == "ETHUSDT"
    assert orders[0]["quantity"] == 1.5


def test_orders_drop_small_reduce_only_notional():
    plan = RebalancePlan(
        world_id="w",
        scale_world=1.0,
        scale_by_strategy={},
        deltas=[SymbolDelta(symbol="BTCUSDT", delta_qty=-0.25, venue="binance")],
    )
    orders = orders_from_world_plan(
        plan,
        options=OrderOptions(
            min_trade_notional=200.0,
            marks_by_symbol={("binance", "BTCUSDT"): 100.0},
        ),
    )
    assert orders == []


def test_orders_normalize_symbol_via_constraints():
    plan = RebalancePlan(
        world_id="w",
        scale_world=1.0,
        scale_by_strategy={},
        deltas=[SymbolDelta(symbol="btc/usdt", delta_qty=1.0, venue="binance")],
    )
    constraints = InstrumentConstraints(
        [
            ConstraintRule(
                venue="binance",
                symbol="BTCUSDT",
                canonical_symbol="BTCUSDT",
                lot_size=0.1,
                aliases=["btc/usdt"],
            )
        ]
    )
    orders = orders_from_world_plan(
        plan,
        options=OrderOptions(
            instrument_constraints=constraints,
        ),
    )
    assert len(orders) == 1
    order = orders[0]
    assert order["symbol"] == "BTCUSDT"
    assert order["quantity"] == 1.0


def test_orders_collect_constraint_violations():
    plan = RebalancePlan(
        world_id="w",
        scale_world=1.0,
        scale_by_strategy={},
        deltas=[SymbolDelta(symbol="BTCUSDT", delta_qty=0.0004, venue="binance")],
    )
    constraints = InstrumentConstraints(
        [ConstraintRule(venue="binance", symbol="BTCUSDT", lot_size=0.001)]
    )
    sink: list = []
    orders = orders_from_world_plan(
        plan,
        options=OrderOptions(
            instrument_constraints=constraints,
            constraint_violation_sink=sink,
        ),
    )
    assert orders == []
    assert len(sink) == 1
    violation = sink[0]
    assert violation.reason == "lot-size"
    assert violation.symbol == "BTCUSDT"


def test_orders_raise_on_constraint_violation():
    plan = RebalancePlan(
        world_id="w",
        scale_world=1.0,
        scale_by_strategy={},
        deltas=[SymbolDelta(symbol="BTCUSDT", delta_qty=0.0004, venue="binance")],
    )
    constraints = InstrumentConstraints(
        [ConstraintRule(venue="binance", symbol="BTCUSDT", lot_size=0.001)]
    )
    with pytest.raises(ConstraintViolationError) as excinfo:
        orders_from_world_plan(
            plan,
            options=OrderOptions(
                instrument_constraints=constraints,
                raise_on_violation=True,
            ),
        )

    assert excinfo.value.violation.symbol == "BTCUSDT"
    assert excinfo.value.violation.reason == "lot-size"


def test_orders_respect_venue_policies():
    plan = RebalancePlan(
        world_id="w",
        scale_world=1.0,
        scale_by_strategy={},
        deltas=[
            SymbolDelta(symbol="BTCUSDT", delta_qty=-0.5, venue="paper-ex"),
        ],
    )
    policies = {
        "paper-ex": VenuePolicy(supports_reduce_only=False, default_time_in_force="IOC"),
    }
    orders = orders_from_world_plan(
        plan,
        options=OrderOptions(venue_policies=policies),
    )
    assert len(orders) == 1
    order = orders[0]
    assert order["time_in_force"] == "IOC"
    assert "reduce_only" not in order

