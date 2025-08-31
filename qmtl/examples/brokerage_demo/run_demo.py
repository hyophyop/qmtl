"""Minimal demo showing BrokerageModel end-to-end usage.

Run with: uv run python qmtl/examples/brokerage_demo/run_demo.py
"""

from __future__ import annotations

from datetime import datetime

from qmtl.brokerage import (
    Account,
    BrokerageModel,
    MarketFillModel,
    PercentFeeModel,
    ConstantSlippageModel,
    SymbolPropertiesProvider,
    ExchangeHoursProvider,
    Order,
    OrderType,
    TimeInForce,
)


def main() -> None:
    model = BrokerageModel(
        buying_power_model=lambda: None,  # type: ignore[assignment]
        fee_model=PercentFeeModel(rate=0.001, minimum=1.0),
        slippage_model=ConstantSlippageModel(0.0005),
        fill_model=MarketFillModel(),
        symbols=SymbolPropertiesProvider(),
        hours=ExchangeHoursProvider.with_us_sample_holidays(require_regular_hours=True),
    )
    # Provide a trivial buying power model inline
    class _BP:
        def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
            return account.cash >= order.price * abs(order.quantity)

    model.buying_power_model = _BP()  # type: ignore[attr-defined]

    acct = Account(cash=10_000.0)
    ts = datetime.utcnow()
    order = Order(symbol="AAPL", quantity=10, price=100.0, type=OrderType.MARKET, tif=TimeInForce.DAY)
    fill = model.execute_order(acct, order, market_price=100.0, ts=ts)
    print({"fill": fill, "cash": acct.cash})


if __name__ == "__main__":
    main()

