"""Tests for simple brokerage model components."""

import pytest

from qmtl.runtime.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    ImmediateFillModel,
    Order,
    PerShareFeeModel,
    VolumeShareSlippageModel,
)


def test_can_submit_order_based_on_buying_power():
    account = Account(cash=1000)
    order = Order(symbol="AAPL", quantity=5, price=100)
    brokerage = BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(),
        VolumeShareSlippageModel(),
        ImmediateFillModel(),
    )
    assert brokerage.can_submit_order(account, order)
    account.cashbook.set(account.base_currency, 100)
    assert not brokerage.can_submit_order(account, order)


def test_execute_order_applies_slippage_and_fee():
    account = Account(cash=1000)
    order = Order(symbol="AAPL", quantity=5, price=100)
    brokerage = BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(fee_per_share=0.5),
        VolumeShareSlippageModel(fallback_pct=0.01),
        ImmediateFillModel(),
    )
    fill = brokerage.execute_order(account, order, market_price=100)
    expected_price = 100 * (1 + 0.01)
    expected_fee = 5 * 0.5
    assert fill.price == expected_price
    assert fill.fee == expected_fee
    assert account.cashbook.get(account.base_currency).balance == 1000 - (
        expected_price * 5 + expected_fee
    )


def test_execute_order_rejects_when_insufficient_cash():
    account = Account(cash=10)
    order = Order(symbol="AAPL", quantity=1, price=100)
    brokerage = BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(),
        VolumeShareSlippageModel(),
        ImmediateFillModel(),
    )
    with pytest.raises(ValueError):
        brokerage.execute_order(account, order, market_price=100)
