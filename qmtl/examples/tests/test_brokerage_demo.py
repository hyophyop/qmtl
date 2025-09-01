from datetime import datetime, timezone

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


def test_demo_executes_market_order():
    # Construct a simple brokerage model akin to the demo
    model = BrokerageModel(
        buying_power_model=lambda: None,  # type: ignore[assignment]
        fee_model=PercentFeeModel(rate=0.001, minimum=1.0),
        slippage_model=ConstantSlippageModel(0.0),
        fill_model=MarketFillModel(),
        symbols=SymbolPropertiesProvider(),
        hours=ExchangeHoursProvider(),
    )

    class _BP:
        def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
            return account.cash >= order.price * abs(order.quantity)

    model.buying_power_model = _BP()  # type: ignore[attr-defined]

    acct = Account(cash=1_000.0)
    order = Order(symbol="AAPL", quantity=5, price=100.0, type=OrderType.MARKET, tif=TimeInForce.DAY)
    fill = model.execute_order(acct, order, market_price=100.0, ts=datetime.now(timezone.utc))
    assert fill.quantity == 5
    # Fee minimum applies: $1
    assert fill.fee >= 1.0
    assert acct.cash <= 1_000.0 - (fill.price * 5)

