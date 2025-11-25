"""Minimal demo showing BrokerageModel end-to-end usage.

Run with: uv run python qmtl/examples/brokerage_demo/run_demo.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from qmtl.runtime.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    ConstantSlippageModel,
    ExchangeHoursProvider,
    MarketFillModel,
    Order,
    OrderType,
    PercentFeeModel,
    SymbolPropertiesProvider,
    TimeInForce,
)


def main() -> None:
    model = BrokerageModel(
        buying_power_model=CashBuyingPowerModel(symbols=SymbolPropertiesProvider()),
        fee_model=PercentFeeModel(rate=0.001, minimum=1.0),
        slippage_model=ConstantSlippageModel(0.0005),
        fill_model=MarketFillModel(),
        symbols=SymbolPropertiesProvider(),
        hours=ExchangeHoursProvider.with_us_sample_holidays(require_regular_hours=True),
    )

    acct = Account(cash=10_000.0)
    ts = datetime.now(timezone.utc)
    order = Order(symbol="AAPL", quantity=10, price=100.0, type=OrderType.MARKET, tif=TimeInForce.DAY)
    fill = model.execute_order(acct, order, market_price=100.0, ts=ts)
    balance = acct.cashbook.get(acct.base_currency).balance
    print({"fill": fill, "cash": balance})


if __name__ == "__main__":
    main()
