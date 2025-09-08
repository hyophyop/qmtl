from datetime import datetime

import pytest

from qmtl.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    Order,
    PerShareFeeModel,
    NullSlippageModel,
    MarketFillModel,
    StaticShortableProvider,
    ShortableLot,
    ibkr_equities_like_profile,
)


def test_shortable_provider_blocks_short_sell_when_not_available():
    account = Account(cash=10_000)
    shortable = StaticShortableProvider({})  # none shortable
    model = BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(),
        NullSlippageModel(),
        MarketFillModel(),
        shortable=shortable,
    )
    order = Order(symbol="AAPL", quantity=-10, price=100.0)
    with pytest.raises(ValueError, match="not shortable"):
        model.can_submit_order(account, order)


def test_shortable_provider_enforces_available_quantity_and_fee():
    account = Account(cash=10_000)
    shortable = StaticShortableProvider({"AAPL": ShortableLot(quantity=5, fee=0.1)})
    model = BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(),
        NullSlippageModel(),
        MarketFillModel(),
        shortable=shortable,
    )
    order = Order(symbol="AAPL", quantity=-3, price=100.0)
    fill = model.execute_order(account, order, market_price=100.0)
    # 3 shares shorted, leaving 2 available
    assert fill.quantity == -3
    assert shortable.available_qty("AAPL") == 2
    # Borrow fee (0.1) + per-share fee (0.01) per share
    assert fill.fee == pytest.approx(3 * (0.1 + 0.01))
    # Requesting more than remaining should be rejected
    with pytest.raises(ValueError, match="Insufficient shortable quantity"):
        model.can_submit_order(account, Order(symbol="AAPL", quantity=-3, price=100.0))


def test_ibkr_equities_like_profile_builds_model():
    profile = ibkr_equities_like_profile()
    model = profile.build()
    assert isinstance(model, BrokerageModel)
    # Basic execution succeeds during regular hours: use a known time
    order = Order(symbol="AAPL", quantity=1, price=100.0)
    fill = model.execute_order(Account(cash=200), order, market_price=100.0)
    assert fill.quantity == 1

