from __future__ import annotations

from qmtl.services.gateway.instrument_constraints import (
    ConstraintRule,
    InstrumentConstraints,
)


def test_constraint_resolution_merges_rules():
    constraints = InstrumentConstraints(
        [
            ConstraintRule(symbol="*", min_notional=25.0),
            ConstraintRule(venue="binance", symbol="*", lot_size=0.1),
            ConstraintRule(
                venue="binance",
                symbol="BTCUSDT",
                canonical_symbol="BTCUSDT",
                lot_size=0.001,
                min_notional=5.0,
                aliases=["btc/usdt"],
            ),
        ]
    )

    resolved = constraints.resolve("binance", "btc/usdt")
    assert resolved.symbol == "BTCUSDT"
    assert resolved.constraint.lot_size == 0.001
    assert resolved.constraint.min_notional == 5.0


def test_constraint_resolution_falls_back_to_wildcard():
    constraints = InstrumentConstraints(
        [
            ConstraintRule(symbol="*", min_notional=50.0),
            ConstraintRule(symbol="ETHUSDT", lot_size=0.05),
        ]
    )

    resolved = constraints.resolve("unknown", "ETHUSDT")
    assert resolved.symbol == "ETHUSDT"
    assert resolved.constraint.min_notional == 50.0
    assert resolved.constraint.lot_size == 0.05
