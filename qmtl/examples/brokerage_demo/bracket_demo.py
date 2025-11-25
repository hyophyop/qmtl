"""
Run with: uv run python qmtl/examples/brokerage_demo/bracket_demo.py
"""

from __future__ import annotations

from qmtl.runtime.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    PerShareFeeModel,
    NullSlippageModel,
    UnifiedFillModel,
    Order,
    OrderType,
    TimeInForce,
    BracketOrder,
)


def main() -> None:
    brk = BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(fee_per_share=0.0),
        NullSlippageModel(),
        UnifiedFillModel(),
    )
    acct = Account(cash=1_000_000.0)

    entry = Order(
        symbol="AAPL",
        quantity=100,
        price=100.0,
        type=OrderType.LIMIT,
        tif=TimeInForce.GTC,
        limit_price=100.0,
    )
    take_profit = Order(
        symbol="AAPL",
        quantity=-100,
        price=100.0,
        type=OrderType.LIMIT,
        tif=TimeInForce.GTC,
        limit_price=110.0,
    )
    stop_loss = Order(
        symbol="AAPL",
        quantity=-100,
        price=100.0,
        type=OrderType.STOP,
        tif=TimeInForce.GTC,
        stop_price=90.0,
    )
    bracket = BracketOrder(entry, take_profit, stop_loss)

    fill_entry, fill_tp, fill_sl = bracket.execute(brk, acct, market_price=100.0)
    fill_entry, fill_tp, fill_sl = bracket.execute(brk, acct, market_price=110.0)
    balance = acct.cashbook.get(acct.base_currency).balance
    print({"entry": fill_entry, "take_profit": fill_tp, "stop_loss": fill_sl, "cash": balance})


if __name__ == "__main__":
    main()
