from __future__ import annotations

from qmtl.services.gateway.rebalancing_executor import (
    OrderOptions,
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
    assert orders[0]["symbol"] == "BTCUSDT" and orders[0]["reduce_only"] is True
    assert orders[1]["symbol"] == "ETHUSDT" and "reduce_only" not in orders[1]

