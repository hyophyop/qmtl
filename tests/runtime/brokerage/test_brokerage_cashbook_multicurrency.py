from datetime import datetime, date, timezone

import pytest

from qmtl.runtime.brokerage import (
    Account,
    BrokerageModel,
    CashWithSettlementBuyingPowerModel,
    MarketFillModel,
    NullSlippageModel,
    Order,
    PerShareFeeModel,
    SettlementModel,
    SymbolProperties,
    SymbolPropertiesProvider,
)


def test_multicurrency_cashbook_and_holiday_settlement():
    holidays = {date(2024, 7, 4)}
    symbols = SymbolPropertiesProvider(
        {
            "AAPL": SymbolProperties("AAPL", currency="USD"),
            "BMW": SymbolProperties("BMW", currency="EUR"),
        }
    )
    settlement = SettlementModel(days=2, defer_cash=True, holidays=holidays)
    bp = CashWithSettlementBuyingPowerModel(settlement, symbols)
    model = BrokerageModel(
        bp,
        PerShareFeeModel(fee_per_share=0.0),
        NullSlippageModel(),
        MarketFillModel(),
        symbols=symbols,
        settlement=settlement,
    )
    acct = Account(cash=1000.0)
    acct.cashbook.set("EUR", 1000.0, rate=1.1)
    # FX conversion before trades
    assert acct.cashbook.total_value("USD") == pytest.approx(1000.0 + 1000.0 * 1.1)

    ts = datetime(2024, 7, 3, tzinfo=timezone.utc)  # day before holiday
    model.execute_order(acct, Order(symbol="AAPL", quantity=5, price=100.0), market_price=100.0, ts=ts)
    model.execute_order(acct, Order(symbol="BMW", quantity=10, price=10.0), market_price=10.0, ts=ts)

    # Cash unchanged until settlement
    assert acct.cashbook.get("USD").balance == 1000.0
    assert acct.cashbook.get("EUR").balance == 1000.0
    assert settlement.reserved_for("USD") == 500.0
    assert settlement.reserved_for("EUR") == 100.0

    # No settlement yet on the Friday after holiday
    early = datetime(2024, 7, 5, tzinfo=timezone.utc)
    assert settlement.apply_due(acct, early) == 0

    # Total value reflects pending debits at FX rate
    assert acct.cashbook.total_value("USD") == pytest.approx(1490.0)

    # Monday after weekend/holiday -> both settle
    later = datetime(2024, 7, 8, tzinfo=timezone.utc)
    applied = settlement.apply_due(acct, later)
    assert applied == 2
    assert acct.cashbook.get("USD").balance == 500.0
    assert acct.cashbook.get("EUR").balance == 900.0
    assert settlement.reserved == 0.0
