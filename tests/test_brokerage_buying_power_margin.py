import pytest

from qmtl.brokerage import (
    Account,
    AccountType,
    BrokerageModel,
    CashBuyingPowerModel,
    ImmediateFillModel,
    Order,
    PerShareFeeModel,
    VolumeShareSlippageModel,
)


def _brokerage():
    return BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(),
        VolumeShareSlippageModel(),
        ImmediateFillModel(),
    )


def test_leverage_limit_rejects_order():
    account = Account(cash=1000, account_type=AccountType.MARGIN, leverage=2)
    order = Order(symbol="AAPL", quantity=21, price=100)
    brokerage = _brokerage()
    assert not brokerage.can_submit_order(account, order)


def test_required_free_buying_power_enforced():
    account = Account(
        cash=1000,
        account_type=AccountType.MARGIN,
        leverage=2,
        required_free_buying_power_percent=0.1,
    )
    brokerage = _brokerage()
    reject = Order(symbol="AAPL", quantity=19, price=100)
    assert not brokerage.can_submit_order(account, reject)
    allow = Order(symbol="AAPL", quantity=18, price=100)
    assert brokerage.can_submit_order(account, allow)
