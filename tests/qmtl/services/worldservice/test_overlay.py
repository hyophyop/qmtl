from __future__ import annotations

import pytest
from qmtl.services.worldservice.rebalancing.overlay import OverlayPlanner
from qmtl.services.worldservice.rebalancing.base import PositionSlice, SymbolDelta
from qmtl.services.worldservice.schemas import OverlayConfigModel


def test_overlay_planner_world_scale_down():
    # World a notional N=60k; scale g=2/3 → d_notional = -20k
    positions = [
        PositionSlice(world_id="a", strategy_id="s1", symbol="BTCUSDT", qty=1.0, mark=60000.0, venue="binance")
    ]
    overlay = OverlayConfigModel(
        instrument_by_world={"a": "BTCUSDT_PERP"},
        price_by_symbol={"BTCUSDT_PERP": 60000.0},
        min_order_notional=0.0,
    )
    deltas = OverlayPlanner().plan(
        positions=positions,
        world_alloc_before={"a": 0.3},
        world_alloc_after={"a": 0.2},
        overlay=overlay,
    )

    assert deltas == [
        SymbolDelta(symbol="BTCUSDT_PERP", delta_qty=pytest.approx(-1 / 3), venue=None)
    ]
