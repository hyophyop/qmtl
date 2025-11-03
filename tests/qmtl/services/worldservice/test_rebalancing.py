from __future__ import annotations

from qmtl.services.worldservice.rebalancing import (
    ProportionalRebalancer,
    RebalanceContext,
    PositionSlice,
    MultiWorldProportionalRebalancer,
    MultiWorldRebalanceContext,
)


def test_single_world_proportional_downscale_rounding():
    # World a scales 0.3 -> 0.2 (gw=2/3). One position: 1 BTC @ 60000.
    # Target notional = 60000 * 2/3 = 40000 -> delta_notional = -20000
    # delta_qty = -20000/60000 = -0.333..., rounded toward zero to -0.333
    ctx = RebalanceContext(
        total_equity=1_000_000.0,
        world_id="a",
        world_alloc_before=0.3,
        world_alloc_after=0.2,
        strategy_alloc_before={"b": 0.1},
        strategy_alloc_after={"b": (0.2 * (1/3))},
        positions=[
            PositionSlice(world_id="a", strategy_id="b", symbol="BTCUSDT", qty=1.0, mark=60000.0, venue="binance")
        ],
        min_trade_notional=0.0,
        lot_size_by_symbol={"BTCUSDT": 0.001},
    )

    plan = ProportionalRebalancer().plan(ctx)
    assert plan.world_id == "a"
    assert abs(plan.scale_world - (0.2 / 0.3)) < 1e-9
    assert len(plan.deltas) == 1
    d = plan.deltas[0]
    assert d.symbol == "BTCUSDT"
    assert d.venue == "binance"
    assert round(d.delta_qty, 3) == -0.333


def test_multi_world_netting_global():
    # World a downscale BTC by -0.333...; world c upscale the same symbol.
    # Global net should reflect aggregation by notional.
    positions = [
        PositionSlice(world_id="a", strategy_id="b", symbol="BTCUSDT", qty=1.0, mark=60000.0, venue="binance"),
        PositionSlice(world_id="c", strategy_id="d", symbol="BTCUSDT", qty=-0.5, mark=60000.0, venue="binance"),
    ]

    mctx = MultiWorldRebalanceContext(
        total_equity=1_000_000.0,
        world_alloc_before={"a": 0.3, "c": 0.2},
        world_alloc_after={"a": 0.2, "c": 0.25},
        positions=positions,
        min_trade_notional=0.0,
        lot_size_by_symbol={"BTCUSDT": 0.001},
    )
    mplan = MultiWorldProportionalRebalancer().plan(mctx)
    assert set(mplan.per_world.keys()) == {"a", "c"}
    # Global deltas could be 1 item (BTCUSDT/binance). We just check it's present.
    assert any(d.symbol == "BTCUSDT" for d in mplan.global_deltas)

