import pytest

from datetime import datetime, time, timezone, timedelta

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
    UnifiedFillModel,
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


def test_volume_limited_partial_fill_ioc():
    account = Account(cash=1_000_000)
    order = Order(symbol="AAPL", quantity=1_000, price=100.0, type=OrderType.MARKET, tif=TimeInForce.IOC)
    brk = make_brokerage(fill=MarketFillModel(volume_limit=0.1))
    fill = brk.execute_order(account, order, market_price=100.0, bar_volume=5_000)
    assert fill.quantity == 500


def test_volume_limited_full_fill_when_order_small():
    account = Account(cash=1_000_000)
    order = Order(symbol="AAPL", quantity=200, price=100.0, type=OrderType.MARKET, tif=TimeInForce.IOC)
    brk = make_brokerage(fill=MarketFillModel(volume_limit=0.1))
    fill = brk.execute_order(account, order, market_price=100.0, bar_volume=5_000)
    assert fill.quantity == 200


def test_volume_limited_no_fill_when_zero_volume():
    account = Account(cash=1_000_000)
    order = Order(symbol="AAPL", quantity=100, price=100.0, type=OrderType.MARKET, tif=TimeInForce.IOC)
    brk = make_brokerage(fill=MarketFillModel(volume_limit=0.1))
    fill = brk.execute_order(account, order, market_price=100.0, bar_volume=0)
    assert fill.quantity == 0


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


def test_gtd_order_respects_expiration():
    account = Account(cash=1_000_000)
    brk = make_brokerage(fill=MarketFillModel())
    now = datetime.now(timezone.utc)
    expired = Order(
        symbol="AAPL",
        quantity=100,
        price=100.0,
        type=OrderType.MARKET,
        tif=TimeInForce.GTD,
        expire_at=now - timedelta(seconds=1),
    )
    fill_expired = brk.execute_order(account, expired, market_price=100.0, ts=now)
    assert fill_expired.quantity == 0

    valid = Order(
        symbol="AAPL",
        quantity=100,
        price=100.0,
        type=OrderType.MARKET,
        tif=TimeInForce.GTD,
        expire_at=now + timedelta(days=1),
    )
    fill_valid = brk.execute_order(account, valid, market_price=100.0, ts=now)
    assert fill_valid.quantity == 100


def test_market_on_open_and_close_fill_only_at_boundaries():
    hours = ExchangeHoursProvider()
    brk = make_brokerage(hours=hours, fill=UnifiedFillModel())
    account = Account(cash=1_000_000)

    today = datetime.now(timezone.utc).date()
    trade_date = today
    while trade_date.weekday() >= 5 or trade_date in hours.holidays:
        trade_date += timedelta(days=1)

    open_ts = datetime.combine(trade_date, hours.market_hours.regular_start)
    later_ts = open_ts + timedelta(minutes=5)

    order_moo = Order(symbol="AAPL", quantity=100, price=100.0, type=OrderType.MOO)
    fill_late = brk.execute_order(account, order_moo, market_price=100.0, ts=later_ts)
    assert fill_late.quantity == 0
    order_moo2 = Order(symbol="AAPL", quantity=100, price=100.0, type=OrderType.MOO)
    fill_open = brk.execute_order(account, order_moo2, market_price=100.0, ts=open_ts)
    assert fill_open.quantity == 100

    close_time = hours.early_closes.get(trade_date, hours.market_hours.regular_end)
    close_ts = datetime.combine(open_ts.date(), close_time)
    before_close = close_ts - timedelta(minutes=1)
    order_moc = Order(symbol="AAPL", quantity=100, price=100.0, type=OrderType.MOC)
    fill_before_close = brk.execute_order(account, order_moc, market_price=100.0, ts=before_close)
    assert fill_before_close.quantity == 0
    order_moc2 = Order(symbol="AAPL", quantity=100, price=100.0, type=OrderType.MOC)
    fill_close = brk.execute_order(account, order_moc2, market_price=100.0, ts=close_ts)
    assert fill_close.quantity == 100


def test_trailing_stop_tracks_and_triggers():
    account = Account(cash=1_000_000)
    brk = make_brokerage(fill=UnifiedFillModel())
    order = Order(
        symbol="AAPL",
        quantity=-100,
        price=100.0,
        type=OrderType.TRAILING_STOP,
        trail_amount=5.0,
    )

    fill1 = brk.execute_order(account, order, market_price=100.0)
    assert fill1.quantity == 0
    assert order.stop_price == 95.0

    fill2 = brk.execute_order(account, order, market_price=110.0)
    assert fill2.quantity == 0
    assert order.stop_price == 105.0

    fill3 = brk.execute_order(account, order, market_price=104.0)
    assert fill3.quantity == -100
    assert fill3.price == 104.0
