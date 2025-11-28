from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from qmtl.examples.brokerage_demo.advanced_demo import build_model
from qmtl.runtime.brokerage import (
    Account,
    ExchangeHoursProvider,
    Order,
    OrderType,
    TimeInForce,
)


def test_brokerage_e2e_scenarios():
    model, settlement = build_model()
    acct = Account(cash=100_000.0)
    hours = cast(ExchangeHoursProvider | None, getattr(model, "hours", None))
    assert hours is not None

    day = datetime(2024, 1, 2, tzinfo=timezone.utc)
    open_ts = datetime.combine(day.date(), hours.market_hours.regular_start, tzinfo=timezone.utc)
    close_time = hours.early_closes.get(day.date(), hours.market_hours.regular_end)
    close_ts = datetime.combine(day.date(), close_time, tzinfo=timezone.utc)

    # MOO fills at open with slippage and fee
    order_moo = Order("AAPL", 10, 100.0, OrderType.MOO)
    fill_moo = model.execute_order(acct, order_moo, 100.0, ts=open_ts)
    assert fill_moo.quantity == 10
    assert fill_moo.price > 100.0
    assert fill_moo.fee >= 1.0

    # IOC partially fills up to liquidity cap
    in_session = open_ts + timedelta(minutes=1)
    order_ioc = Order("AAPL", 100, 100.0, OrderType.MARKET, tif=TimeInForce.IOC)
    fill_ioc = model.execute_order(acct, order_ioc, 100.0, ts=in_session)
    assert fill_ioc.quantity == 50

    # FOK fails when full quantity unavailable
    order_fok = Order("AAPL", 60, 100.0, OrderType.MARKET, tif=TimeInForce.FOK)
    fill_fok = model.execute_order(acct, order_fok, 100.0, ts=in_session)
    assert fill_fok.quantity == 0

    # MOC fills only at close
    before_close = close_ts - timedelta(minutes=1)
    early = model.execute_order(acct, Order("AAPL", 10, 100.0, OrderType.MOC), 100.0, ts=before_close)
    assert early.quantity == 0
    order_moc = Order("AAPL", 10, 100.0, OrderType.MOC)
    fill_moc = model.execute_order(acct, order_moc, 100.0, ts=close_ts)
    assert fill_moc.quantity == 10

    # Market closed on holiday
    holiday_ts = datetime(2024, 7, 4, 15, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Market is closed"):
        model.can_submit_order(acct, order_moo, ts=holiday_ts)

    # Deferred settlement keeps cash unchanged until applied
    balance = acct.cashbook.get(acct.base_currency).balance
    assert balance == pytest.approx(100_000.0)
    settlement.apply_due(acct, now=close_ts + timedelta(days=1))
    updated_balance = acct.cashbook.get(acct.base_currency).balance
    assert updated_balance < 100_000.0
