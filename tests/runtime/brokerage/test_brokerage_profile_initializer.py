"""Tests for BrokerageProfile overrides and SecurityInitializer mapping."""

from qmtl.runtime.brokerage import (
    BrokerageProfile,
    SecurityInitializer,
    CashBuyingPowerModel,
    ImmediateFillModel,
    PerShareFeeModel,
    SpreadBasedSlippageModel,
    ibkr_equities_like_profile,
)


def _alt_profile() -> BrokerageProfile:
    return BrokerageProfile(
        buying_power=CashBuyingPowerModel(),
        fee=PerShareFeeModel(fee_per_share=0.0),
        slippage=SpreadBasedSlippageModel(spread_fraction=0.1),
        fill=ImmediateFillModel(),
    )


def test_brokerage_profile_override_creates_modified_copy():
    profile = ibkr_equities_like_profile()
    overridden = profile.override(fee=PerShareFeeModel(fee_per_share=0.0))
    assert overridden.fee.fee_per_share == 0.0
    # original profile should remain unchanged
    assert profile.fee.fee_per_share == 0.005


def test_security_initializer_resolves_profiles_and_calls_hook():
    default_profile = ibkr_equities_like_profile()
    forex_profile = _alt_profile()
    called = []

    def hook(model, symbol):
        called.append(symbol)
        return model

    initializer = SecurityInitializer(
        default_profile,
        profiles_by_symbol={"SPY": forex_profile},
        profiles_by_asset_class={"forex": forex_profile},
        classify=lambda s: "forex" if s == "EURUSD" else "equity",
        override=hook,
    )

    spy_model = initializer.for_symbol("SPY")
    fx_model = initializer.for_symbol("EURUSD")
    eq_model = initializer.for_symbol("AAPL")

    assert spy_model.fee_model.fee_per_share == 0.0
    assert fx_model.fee_model.fee_per_share == 0.0
    assert eq_model.fee_model.fee_per_share == 0.005
    assert called == ["SPY", "EURUSD", "AAPL"]
