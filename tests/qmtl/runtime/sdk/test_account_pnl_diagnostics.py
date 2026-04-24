from __future__ import annotations

import pytest

from qmtl.runtime.sdk.diagnostics import AccountFill, summarize_account_pnl
from qmtl.runtime.sdk.execution_modeling import ExecutionFill, OrderSide


def test_summarize_account_pnl_realized_unrealized_and_fees() -> None:
    summary = summarize_account_pnl(
        [
            AccountFill("AAPL", 10, 100.0, commission=1.0),
            AccountFill("AAPL", -4, 110.0, commission=0.5),
        ],
        marks={"AAPL": 120.0},
        starting_cash=1_000.0,
    )

    assert summary.ending_cash == pytest.approx(438.5)
    assert summary.realized_pnl == pytest.approx(40.0)
    assert summary.unrealized_pnl == pytest.approx(120.0)
    assert summary.fees == pytest.approx(1.5)
    assert summary.equity == pytest.approx(1_158.5)
    assert summary.total_pnl == pytest.approx(158.5)

    position = summary.positions["AAPL"]
    assert position.quantity == pytest.approx(6.0)
    assert position.avg_cost == pytest.approx(100.0)
    assert position.mark_price == pytest.approx(120.0)


def test_summarize_account_pnl_accepts_execution_fill_shape() -> None:
    fills = [
        ExecutionFill(
            order_id="buy-1",
            symbol="MSFT",
            side=OrderSide.BUY,
            quantity=2.0,
            requested_price=50.0,
            fill_price=51.0,
            fill_time=1,
            commission=0.25,
            slippage=1.0,
            market_impact=0.0,
        ),
        {
            "symbol": "MSFT",
            "side": "sell",
            "quantity": 1.0,
            "fill_price": 60.0,
            "fee": 0.10,
        },
    ]

    summary = summarize_account_pnl(fills, marks={"MSFT": 55.0})

    assert summary.realized_pnl == pytest.approx(9.0)
    assert summary.unrealized_pnl == pytest.approx(4.0)
    assert summary.fees == pytest.approx(0.35)
    assert summary.total_pnl == pytest.approx(12.65)


def test_summarize_account_pnl_handles_short_positions_and_flips() -> None:
    summary = summarize_account_pnl(
        [
            {"symbol": "BTC", "quantity": -3.0, "price": 100.0},
            {"symbol": "BTC", "quantity": 5.0, "price": 90.0},
        ],
        marks={"BTC": 95.0},
    )

    assert summary.realized_pnl == pytest.approx(30.0)
    assert summary.unrealized_pnl == pytest.approx(10.0)
    assert summary.total_pnl == pytest.approx(40.0)
    assert summary.positions["BTC"].quantity == pytest.approx(2.0)
    assert summary.positions["BTC"].avg_cost == pytest.approx(90.0)


def test_summarize_account_pnl_uses_last_fill_price_when_mark_missing() -> None:
    summary = summarize_account_pnl([AccountFill("ETH", 2.0, 10.0)])

    assert summary.unrealized_pnl == pytest.approx(0.0)
    assert summary.equity == pytest.approx(0.0)
    assert summary.positions["ETH"].mark_price == pytest.approx(10.0)


def test_summarize_account_pnl_rejects_invalid_fill_values() -> None:
    with pytest.raises(ValueError, match="quantity"):
        summarize_account_pnl([{"symbol": "AAPL", "quantity": 0, "price": 100.0}])

    with pytest.raises(ValueError, match="price"):
        summarize_account_pnl([{"symbol": "AAPL", "quantity": 1, "price": 0.0}])

    with pytest.raises(ValueError, match="commission"):
        summarize_account_pnl([AccountFill("AAPL", 1, 100.0, commission=-1.0)])
