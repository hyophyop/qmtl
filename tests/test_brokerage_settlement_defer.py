from datetime import datetime, timedelta, timezone

from qmtl.runtime.brokerage import (
    Account,
    BrokerageModel,
    CashWithSettlementBuyingPowerModel,
    MarketFillModel,
    PerShareFeeModel,
    NullSlippageModel,
    SettlementModel,
    Order,
)


def test_deferred_settlement_reserves_cash_and_applies_later():
    settlement = SettlementModel(days=1, defer_cash=True)
    bp = CashWithSettlementBuyingPowerModel(settlement)
    model = BrokerageModel(
        bp,
        PerShareFeeModel(fee_per_share=0.0),
        NullSlippageModel(),
        MarketFillModel(),
        settlement=settlement,
    )
    acct = Account(cash=1000.0)

    order = Order(symbol="AAPL", quantity=5, price=100.0)
    # Buying power respects reserved cash (initially none)
    assert model.can_submit_order(acct, order)
    fill = model.execute_order(acct, order, market_price=100.0, ts=datetime.now(timezone.utc))
    assert fill.quantity == 5
    # Cash not moved immediately
    assert acct.cash == 1000.0
    # But reserved increased
    assert settlement.reserved >= 500.0
    # Next day, apply settlement reduces cash
    next_day = datetime.now(timezone.utc) + timedelta(days=1)
    applied = settlement.apply_due(acct, now=next_day)
    assert applied >= 1
    assert acct.cash == 500.0

