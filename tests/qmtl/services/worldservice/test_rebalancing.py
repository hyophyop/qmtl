from __future__ import annotations

import pytest

from qmtl.services.worldservice.rebalancing import (
    ProportionalRebalancer,
    RebalanceContext,
    PositionSlice,
    MultiWorldProportionalRebalancer,
    MultiWorldRebalanceContext,
    StrategyAllocationCalculator,
    GlobalDeltaAggregator,
    RebalancePlan,
    SymbolDelta,
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


def test_lot_rounding_toward_zero_on_upscale():
    ctx = RebalanceContext(
        total_equity=1_000_000.0,
        world_id="x",
        world_alloc_before=0.1,
        world_alloc_after=0.11,
        strategy_alloc_before={"s": 0.1},
        strategy_alloc_after={"s": 0.11},
        positions=[
            PositionSlice(
                world_id="x",
                strategy_id="s",
                symbol="ETHUSDT",
                qty=1.0,
                mark=2_000.0,
                venue="binance",
            )
        ],
        min_trade_notional=0.0,
        lot_size_by_symbol={"ETHUSDT": 0.07},
    )

    plan = ProportionalRebalancer().plan(ctx)
    assert len(plan.deltas) == 1
    delta = plan.deltas[0]
    assert delta.symbol == "ETHUSDT"
    # Raw quantity delta would be 0.1; rounding should move toward zero to 0.07.
    assert delta.delta_qty == pytest.approx(0.07, abs=1e-9)


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


def test_strategy_override_world_scale_no_change_when_after_equals_before():
    # World a downscales (0.3->0.2; gw=2/3) but strategy b increases share so
    # that its total-equity allocation remains the same (before=0.1, after=0.1).
    # Expected: b's positions are not scaled (factor=1.0), so delta ~ 0.
    positions = [
        PositionSlice(world_id="a", strategy_id="b", symbol="BTCUSDT", qty=1.0, mark=60000.0, venue="binance"),
    ]

    ctx = RebalanceContext(
        total_equity=1_000_000.0,
        world_id="a",
        world_alloc_before=0.3,
        world_alloc_after=0.2,
        strategy_alloc_before={"b": 0.1},
        strategy_alloc_after={"b": 0.1},  # stays at 10% of total equity
        positions=positions,
        min_trade_notional=0.0,
        lot_size_by_symbol={"BTCUSDT": 0.001},
    )
    plan = ProportionalRebalancer().plan(ctx)
    assert len(plan.deltas) == 0 or abs(plan.deltas[0].delta_qty) < 1e-6


def test_lot_rounding_aggregates_across_slices_on_boundary():
    positions = [
        PositionSlice(
            world_id="w",
            strategy_id="s1",
            symbol="ETHUSDT",
            qty=1.0,
            mark=100.0,
            venue="binance",
        ),
        PositionSlice(
            world_id="w",
            strategy_id="s2",
            symbol="ETHUSDT",
            qty=1.0,
            mark=100.0,
            venue="binance",
        ),
    ]
    ctx = RebalanceContext(
        total_equity=1_000_000.0,
        world_id="w",
        world_alloc_before=0.2,
        world_alloc_after=0.1,
        strategy_alloc_before={"s1": 0.1, "s2": 0.1},
        strategy_alloc_after={"s1": 0.05, "s2": 0.05},
        positions=positions,
        min_trade_notional=0.0,
        lot_size_by_symbol={"ETHUSDT": 0.25},
    )

    plan = ProportionalRebalancer().plan(ctx)
    assert len(plan.deltas) == 1
    delta = plan.deltas[0]
    assert delta.symbol == "ETHUSDT"
    # Aggregate delta notionals (two slices) land exactly on a 0.25 lot boundary.
    assert delta.delta_qty == pytest.approx(-1.0, abs=1e-9)


def test_min_trade_notional_suppresses_small_delta():
    ctx = RebalanceContext(
        total_equity=1_000_000.0,
        world_id="m",
        world_alloc_before=0.2,
        world_alloc_after=0.199,
        strategy_alloc_before={"s": 0.2},
        strategy_alloc_after={"s": 0.199},
        positions=[
            PositionSlice(
                world_id="m",
                strategy_id="s",
                symbol="BTCUSDT",
                qty=1.0,
                mark=100.0,
                venue="binance",
            )
        ],
        min_trade_notional=1.0,
        lot_size_by_symbol={"BTCUSDT": 0.001},
    )

    plan = ProportionalRebalancer().plan(ctx)
    assert plan.deltas == []


def test_missing_mark_skips_delta():
    ctx = RebalanceContext(
        total_equity=1_000_000.0,
        world_id="z",
        world_alloc_before=0.1,
        world_alloc_after=0.0,
        strategy_alloc_before={"s": 0.1},
        strategy_alloc_after={"s": 0.0},
        positions=[
            PositionSlice(
                world_id="z",
                strategy_id="s",
                symbol="DOGEUSDT",
                qty=1.0,
                mark=-100.0,
                venue="binance",
            )
        ],
        min_trade_notional=0.0,
        lot_size_by_symbol={"DOGEUSDT": 1.0},
    )

    plan = ProportionalRebalancer().plan(ctx)
    assert plan.deltas == []


def test_multi_world_handles_zero_total_equity_when_estimating_strategy_weights():
    positions = [
        PositionSlice(
            world_id="z",
            strategy_id="s",
            symbol="BTCUSDT",
            qty=1.0,
            mark=10_000.0,
            venue="binance",
        )
    ]

    ctx = MultiWorldRebalanceContext(
        total_equity=0.0,
        world_alloc_before={"z": 0.4},
        world_alloc_after={"z": 0.4},
        positions=positions,
        min_trade_notional=0.0,
        lot_size_by_symbol={"BTCUSDT": 0.001},
    )

    plan = MultiWorldProportionalRebalancer().plan(ctx)

    assert plan.per_world["z"].scale_world == pytest.approx(1.0)
    assert plan.global_deltas == []


def test_strategy_allocation_calculator_infers_targets_from_positions():
    ctx = MultiWorldRebalanceContext(
        total_equity=1_000_000.0,
        world_alloc_before={"w": 0.2},
        world_alloc_after={"w": 0.3},
        positions=[],
        min_trade_notional=0.0,
        lot_size_by_symbol=None,
    )
    calculator = StrategyAllocationCalculator(ctx)
    positions = [
        PositionSlice(
            world_id="w",
            strategy_id="s1",
            symbol="BTCUSDT",
            qty=1.0,
            mark=200_000.0,
            venue="binance",
        ),
        PositionSlice(
            world_id="w",
            strategy_id="s2",
            symbol="ETHUSDT",
            qty=10.0,
            mark=2_000.0,
            venue="binance",
        ),
    ]

    targets = calculator.derive("w", positions)

    expected_s1 = (1.0 * 200_000.0) / 1_000_000.0
    expected_s2 = (10.0 * 2_000.0) / 1_000_000.0
    scale_factor = 0.3 / 0.2

    assert targets.before == pytest.approx({"s1": expected_s1, "s2": expected_s2})
    assert targets.after == pytest.approx({"s1": expected_s1 * scale_factor, "s2": expected_s2 * scale_factor})


def test_global_delta_aggregator_averages_marks_per_symbol():
    ctx = MultiWorldRebalanceContext(
        total_equity=1_000_000.0,
        world_alloc_before={"w": 0.2},
        world_alloc_after={"w": 0.2},
        positions=[],
        min_trade_notional=100.0,
        lot_size_by_symbol=None,
    )
    aggregator = GlobalDeltaAggregator(ctx)
    positions = [
        PositionSlice(
            world_id="w",
            strategy_id="s",
            symbol="BTCUSDT",
            qty=1.0,
            mark=30_000.0,
            venue="binance",
        ),
        PositionSlice(
            world_id="w",
            strategy_id="s2",
            symbol="BTCUSDT",
            qty=0.5,
            mark=30_000.0,
            venue="binance",
        ),
    ]
    plan = RebalancePlan(
        world_id="w",
        scale_world=1.0,
        scale_by_strategy={"s": 1.0},
        deltas=[SymbolDelta(symbol="BTCUSDT", delta_qty=-0.75, venue="binance")],
    )

    aggregator.ingest(positions, plan)
    global_deltas = aggregator.build()

    assert len(global_deltas) == 1
    delta = global_deltas[0]
    assert delta.symbol == "BTCUSDT"
    assert delta.venue == "binance"
    assert delta.delta_qty == pytest.approx(-0.75, abs=1e-9)
