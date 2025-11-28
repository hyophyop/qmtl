from datetime import datetime, timezone

from qmtl.runtime.brokerage import (
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
    class _BP:
        def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
            balance = account.cashbook.get(account.base_currency).balance
            return balance >= order.price * abs(order.quantity)

    buying_power = _BP()
    model = BrokerageModel(
        buying_power_model=buying_power,
        fee_model=PercentFeeModel(rate=0.001, minimum=1.0),
        slippage_model=ConstantSlippageModel(0.0),
        fill_model=MarketFillModel(),
        symbols=SymbolPropertiesProvider(),
        hours=ExchangeHoursProvider(),
    )

    acct = Account(cash=1_000.0)
    order = Order(symbol="AAPL", quantity=5, price=100.0, type=OrderType.MARKET, tif=TimeInForce.DAY)
    # Use a fixed timestamp during regular market hours to avoid flaky behavior
    ts = datetime(2024, 1, 5, 15, 0, tzinfo=timezone.utc)
    fill = model.execute_order(acct, order, market_price=100.0, ts=ts)
    assert fill.quantity == 5
    # Fee minimum applies: $1
    assert fill.fee >= 1.0
    balance = acct.cashbook.get(acct.base_currency).balance
    assert balance <= 1_000.0 - (fill.price * 5)
