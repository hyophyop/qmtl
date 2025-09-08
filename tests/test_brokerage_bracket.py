from qmtl.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    PerShareFeeModel,
    NullSlippageModel,
    UnifiedFillModel,
    Order,
    OrderType,
    TimeInForce,
    BracketOrder,
)


def make_brokerage(*, liquidity_cap: int | None = None) -> BrokerageModel:
    return BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(fee_per_share=0.0),
        NullSlippageModel(),
        UnifiedFillModel(liquidity_cap=liquidity_cap),
    )


def test_bracket_full_fill_and_exit() -> None:
    account = Account(cash=1_000_000)
    entry = Order(
        symbol="AAPL",
        quantity=100,
        price=100.0,
        type=OrderType.LIMIT,
        tif=TimeInForce.DAY,
        limit_price=100.0,
    )
    take_profit = Order(
        symbol="AAPL",
        quantity=-100,
        price=100.0,
        type=OrderType.LIMIT,
        tif=TimeInForce.DAY,
        limit_price=110.0,
    )
    stop_loss = Order(
        symbol="AAPL",
        quantity=-100,
        price=100.0,
        type=OrderType.STOP,
        tif=TimeInForce.DAY,
        stop_price=90.0,
    )
    bracket = BracketOrder(entry, take_profit, stop_loss)
    brk = make_brokerage()

    fill_entry, fill_tp, fill_sl = bracket.execute(brk, account, market_price=100.0)
    assert fill_entry.quantity == 100
    assert fill_tp.quantity == 0
    assert fill_sl.quantity == 0

    fill_entry, fill_tp, fill_sl = bracket.execute(brk, account, market_price=110.0)
    assert fill_entry.quantity == 0
    assert fill_tp.quantity == -100
    assert fill_sl.quantity == 0


def test_bracket_partials_adjust_oco() -> None:
    account = Account(cash=1_000_000)
    entry = Order(
        symbol="AAPL",
        quantity=100,
        price=100.0,
        type=OrderType.LIMIT,
        tif=TimeInForce.DAY,
        limit_price=100.0,
    )
    take_profit = Order(
        symbol="AAPL",
        quantity=-100,
        price=100.0,
        type=OrderType.LIMIT,
        tif=TimeInForce.DAY,
        limit_price=110.0,
    )
    stop_loss = Order(
        symbol="AAPL",
        quantity=-100,
        price=100.0,
        type=OrderType.STOP,
        tif=TimeInForce.DAY,
        stop_price=90.0,
    )
    bracket = BracketOrder(entry, take_profit, stop_loss)
    brk = make_brokerage(liquidity_cap=50)

    fill_entry, fill_tp, fill_sl = bracket.execute(brk, account, market_price=100.0)
    assert fill_entry.quantity == 50
    assert bracket.oco is not None
    assert bracket.oco.first.quantity == -50
    assert fill_tp.quantity == 0
    assert fill_sl.quantity == 0

    fill_entry, fill_tp, fill_sl = bracket.execute(brk, account, market_price=100.0)
    assert fill_entry.quantity == 50
    assert bracket.oco is not None
    assert bracket.oco.first.quantity == -100
    assert fill_tp.quantity == 0
    assert fill_sl.quantity == 0
