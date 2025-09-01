import pytest

from datetime import datetime, time, timezone

from qmtl.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    Order,
    OrderType,
    TimeInForce,
    MarketFillModel,
    LimitFillModel,
    PerShareFeeModel,
    NullSlippageModel,
    SymbolPropertiesProvider,
    ExchangeHoursProvider,
)


def make_brokerage(symbols=None, hours=None, fill=None):
    return BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(fee_per_share=0.0),
        NullSlippageModel(),
        fill or MarketFillModel(),
        symbols=symbols,
        hours=hours,
    )


def test_market_order_fok_and_ioc_fill_full_when_liquidity_unlimited():
    account = Account(cash=1_000_000)
    order_ioc = Order(symbol="AAPL", quantity=100, price=100.0, type=OrderType.MARKET, tif=TimeInForce.IOC)
    order_fok = Order(symbol="AAPL", quantity=100, price=100.0, type=OrderType.MARKET, tif=TimeInForce.FOK)
    brk = make_brokerage(fill=MarketFillModel())

    fill_ioc = brk.execute_order(account, order_ioc, market_price=100.0)
    assert fill_ioc.quantity == 100
    fill_fok = brk.execute_order(account, order_fok, market_price=100.0)
    assert fill_fok.quantity == 100


def test_limit_order_not_crossed_does_not_fill():
    account = Account(cash=1_000_000)
    # Buy limit below market should not fill
    order = Order(
        symbol="AAPL",
        quantity=100,
        price=100.0,
        type=OrderType.LIMIT,
        tif=TimeInForce.DAY,
        limit_price=99.0,
    )
    brk = make_brokerage(fill=LimitFillModel())
    fill = brk.execute_order(account, order, market_price=100.0)
    assert fill.quantity == 0


def test_limit_order_crosses_and_fok_requires_full_fill():
    account = Account(cash=1_000_000)
    # Buy limit above market -> can cross
    order = Order(
        symbol="AAPL",
        quantity=100,
        price=100.0,
        type=OrderType.LIMIT,
        tif=TimeInForce.FOK,
        limit_price=101.0,
    )
    brk = make_brokerage(fill=LimitFillModel())
    fill = brk.execute_order(account, order, market_price=100.0)
    assert fill.quantity == 100
    # Expect conservative buy price = min(market, limit)
    assert fill.price == 100.0


def test_ioc_partial_fill_with_liquidity_cap():
    account = Account(cash=1_000_000)
    order = Order(symbol="AAPL", quantity=100, price=100.0, type=OrderType.MARKET, tif=TimeInForce.IOC)
    # Cap immediate liquidity to 30 shares
    brk = make_brokerage(fill=MarketFillModel(liquidity_cap=30))
    fill = brk.execute_order(account, order, market_price=100.0)
    assert fill.quantity == 30


def test_symbol_properties_validation_enforces_tick_and_lot():
    symbols = SymbolPropertiesProvider()
    brk = make_brokerage(symbols=symbols, fill=MarketFillModel())
    account = Account(cash=1_000_000)
    # Invalid tick: 100.003 not aligned to 0.01
    bad_order = Order(symbol="AAPL", quantity=1, price=100.003, type=OrderType.MARKET)
    with pytest.raises(ValueError, match="not aligned to tick"):
        brk.can_submit_order(account, bad_order)
    # Invalid lot: quantity 0
    bad_qty = Order(symbol="AAPL", quantity=0, price=100.0, type=OrderType.MARKET)
    with pytest.raises(ValueError, match="below min"):
        brk.can_submit_order(account, bad_qty)


def test_exchange_hours_provider_blocks_when_closed():
    # Pre/post not allowed and require regular hours
    hours = ExchangeHoursProvider(allow_pre_post_market=False, require_regular_hours=True)
    brk = make_brokerage(hours=hours)
    account = Account(cash=1_000_000)
    order = Order(symbol="AAPL", quantity=1, price=100.0)
    # 3:00 AM US/Eastern equivalent naive: treat as closed (MarketHours defaults assume US equities)
    ts = datetime.combine(datetime.now(timezone.utc).date(), time(3, 0))
    with pytest.raises(ValueError, match="Market is closed"):
        brk.can_submit_order(account, order, ts=ts)
