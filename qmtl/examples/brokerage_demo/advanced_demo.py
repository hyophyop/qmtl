"""Comprehensive brokerage demo covering order types, fees, slippage, hours and settlement.

Run with:
    uv run python qmtl/examples/brokerage_demo/advanced_demo.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qmtl.brokerage import (
    Account,
    BrokerageModel,
    CashWithSettlementBuyingPowerModel,
    ConstantSlippageModel,
    PercentFeeModel,
    SymbolPropertiesProvider,
    ExchangeHoursProvider,
    UnifiedFillModel,
    SettlementModel,
    Order,
    OrderType,
    TimeInForce,
)


def build_model() -> tuple[BrokerageModel, SettlementModel]:
    """Return a demo brokerage model with deferred settlement."""

    settlement = SettlementModel(days=1, defer_cash=True)
    model = BrokerageModel(
        CashWithSettlementBuyingPowerModel(settlement),
        PercentFeeModel(rate=0.001, minimum=1.0),
        ConstantSlippageModel(0.01),
        UnifiedFillModel(liquidity_cap=50),
        symbols=SymbolPropertiesProvider(),
        hours=ExchangeHoursProvider.with_us_sample_holidays(require_regular_hours=True),
        settlement=settlement,
    )
    return model, settlement


def main() -> None:
    model, settlement = build_model()
    acct = Account(cash=100_000.0)
    hours = model.hours  # type: ignore[attr-defined]
    today = datetime(2024, 1, 2, tzinfo=timezone.utc)
    open_ts = datetime.combine(today.date(), hours.market_hours.regular_start, tzinfo=timezone.utc)
    close_time = hours.early_closes.get(today.date(), hours.market_hours.regular_end)
    close_ts = datetime.combine(today.date(), close_time, tzinfo=timezone.utc)

    order_moo = Order("AAPL", 10, 100.0, OrderType.MOO)
    fill_moo = model.execute_order(acct, order_moo, 100.0, ts=open_ts)

    in_session = open_ts + timedelta(minutes=1)
    order_ioc = Order("AAPL", 100, 100.0, OrderType.MARKET, tif=TimeInForce.IOC)
    fill_ioc = model.execute_order(acct, order_ioc, 100.0, ts=in_session)

    order_fok = Order("AAPL", 60, 100.0, OrderType.MARKET, tif=TimeInForce.FOK)
    fill_fok = model.execute_order(acct, order_fok, 100.0, ts=in_session)

    order_moc = Order("AAPL", 10, 100.0, OrderType.MOC)
    fill_moc = model.execute_order(acct, order_moc, 100.0, ts=close_ts)

    try:
        holiday_ts = datetime(2024, 7, 4, 15, 0, tzinfo=timezone.utc)
        model.can_submit_order(acct, order_moo, ts=holiday_ts)
        closed = None
    except ValueError as exc:  # market closed
        closed = str(exc)

    settlement.apply_due(acct, now=close_ts + timedelta(days=1))

    print(
        {
            "moo": fill_moo,
            "ioc": fill_ioc,
            "fok": fill_fok,
            "moc": fill_moc,
            "closed": closed,
            "cash": acct.cash,
        }
    )


if __name__ == "__main__":  # pragma: no cover - manual demo
    main()
