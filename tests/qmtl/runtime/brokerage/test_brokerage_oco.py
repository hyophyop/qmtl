from qmtl.runtime.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    PerShareFeeModel,
    NullSlippageModel,
    UnifiedFillModel,
    Order,
    OrderType,
    TimeInForce,
    OCOOrder,
)


def make_brokerage():
    return BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(fee_per_share=0.0),
        NullSlippageModel(),
        UnifiedFillModel(),
    )


def test_oco_cancels_unfilled_leg():
    account = Account(cash=1_000_000)
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
    oco = OCOOrder(take_profit, stop_loss)
    brk = make_brokerage()

    fill_tp, fill_sl = oco.execute(brk, account, market_price=110.0)
    assert fill_tp.quantity == -100
    assert fill_sl.quantity == 0
