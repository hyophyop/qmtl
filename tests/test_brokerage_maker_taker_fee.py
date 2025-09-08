"""Tests for maker/taker fee model."""

import pytest

from qmtl.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    ImmediateFillModel,
    MakerTakerFeeModel,
    NullSlippageModel,
    Order,
    OrderType,
)


def test_maker_taker_fee_affects_pnl():
    maker_account = Account(cash=10000)
    taker_account = Account(cash=10000)
    fee_model = MakerTakerFeeModel(maker_rate=0.001, taker_rate=0.002)
    brokerage = BrokerageModel(
        CashBuyingPowerModel(),
        fee_model,
        NullSlippageModel(),
        ImmediateFillModel(),
    )

    limit_order = Order(
        symbol="AAPL",
        quantity=10,
        price=100,
        type=OrderType.LIMIT,
        limit_price=100,
    )
    market_order = Order(symbol="AAPL", quantity=10, price=100, type=OrderType.MARKET)

    fill_maker = brokerage.execute_order(maker_account, limit_order, market_price=100)
    fill_taker = brokerage.execute_order(taker_account, market_order, market_price=100)

    assert fill_taker.fee > fill_maker.fee
    assert maker_account.cash - taker_account.cash == pytest.approx(
        fill_taker.fee - fill_maker.fee
    )
