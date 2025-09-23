import pytest

import pytest

from qmtl.runtime.brokerage import (
    Account,
    BrokerageModel,
    CashBuyingPowerModel,
    MarketFillModel,
    PerShareFeeModel,
    NullSlippageModel,
    Order,
    OrderType,
    SymbolPropertiesProvider,
)


def make_brokerage(symbols=None):
    return BrokerageModel(
        CashBuyingPowerModel(),
        PerShareFeeModel(fee_per_share=0.0),
        NullSlippageModel(),
        MarketFillModel(),
        symbols=symbols,
    )


def test_futures_tick_and_multiplier():
    symbols = SymbolPropertiesProvider()
    brk = make_brokerage(symbols=symbols)
    account = Account(cash=1_000_000)
    bad_order = Order(symbol="ES", quantity=1, price=100.1, type=OrderType.MARKET)
    with pytest.raises(ValueError, match="not aligned"):
        brk.can_submit_order(account, bad_order)
    sp = symbols.get("ES")
    assert sp.asset_class == "futures"
    assert sp.contract_multiplier == 50


def test_option_minimum_quantity():
    symbols = SymbolPropertiesProvider()
    brk = make_brokerage(symbols=symbols)
    account = Account(cash=1_000_000)
    bad_order = Order(symbol="AAPL2201C150", quantity=50, price=1.0, type=OrderType.MARKET)
    with pytest.raises(ValueError, match="below min"):
        brk.can_submit_order(account, bad_order)
    good_order = Order(symbol="AAPL2201C150", quantity=100, price=1.0, type=OrderType.MARKET)
    assert brk.can_submit_order(account, good_order)
