import sys
import types

import pytest


def _install_ccxt_stub(markets: dict | None = None, trading_fee: tuple[float, float] | None = None):
    """Install a minimal ccxt stub module into sys.modules for tests."""

    # shared counter across instances
    calls = {"load_markets": 0}

    class _FakeExchange:
        def __init__(self, config):
            self.config = config
            self._markets = markets or {}
            mk, tk = trading_fee if trading_fee is not None else (None, None)
            self.fees = {"trading": {"maker": mk, "taker": tk}}

        def load_markets(self):
            calls["load_markets"] += 1
            return self._markets

        def set_sandbox_mode(self, enabled: bool):  # pragma: no cover - trivial
            self._sandbox = bool(enabled)

        # Older versions naming
        def setSandboxMode(self, enabled: bool):  # pragma: no cover - trivial
            self._sandbox = bool(enabled)

    stub = types.SimpleNamespace()
    stub.exchanges = ["binance", "kraken", "binanceusdm"]
    stub.binance = _FakeExchange
    stub.binanceusdm = _FakeExchange
    stub._calls = calls

    sys.modules["ccxt"] = stub
    return stub


def test_symbol_specific_fees_take_precedence(monkeypatch):
    # Ensure a clean slate
    sys.modules.pop("ccxt", None)
    markets = {
        "BTC/USDT": {"maker": 0.001, "taker": 0.002},
        "ETH/USDT": {"maker": 0.003, "taker": 0.004},
    }
    _install_ccxt_stub(markets=markets, trading_fee=(0.01, 0.02))

    from qmtl.runtime.brokerage.ccxt_profile import make_ccxt_brokerage
    import qmtl.runtime.brokerage.ccxt_profile as cp
    cp._FEE_CACHE.clear()

    model = make_ccxt_brokerage(
        "binance", product="spot", symbol="BTC/USDT", detect_fees=True
    )
    fee = model.fee_model
    from qmtl.runtime.brokerage.fees import MakerTakerFeeModel

    assert isinstance(fee, MakerTakerFeeModel)
    assert fee.maker_rate == pytest.approx(0.001)
    assert fee.taker_rate == pytest.approx(0.002)


def test_exchange_level_fees_used_when_no_markets():
    sys.modules.pop("ccxt", None)
    _install_ccxt_stub(markets={}, trading_fee=(0.005, 0.007))
    from qmtl.runtime.brokerage.ccxt_profile import make_ccxt_brokerage
    import qmtl.runtime.brokerage.ccxt_profile as cp
    cp._FEE_CACHE.clear()

    model = make_ccxt_brokerage("binance", product="spot", detect_fees=True)
    fee = model.fee_model
    from qmtl.runtime.brokerage.fees import MakerTakerFeeModel

    assert isinstance(fee, MakerTakerFeeModel)
    assert fee.maker_rate == pytest.approx(0.005)
    assert fee.taker_rate == pytest.approx(0.007)


def test_defaults_used_when_ccxt_absent_or_detection_disabled(monkeypatch):
    # Ensure ccxt is not importable
    sys.modules.pop("ccxt", None)

    from qmtl.runtime.brokerage.ccxt_profile import make_ccxt_brokerage
    import qmtl.runtime.brokerage.ccxt_profile as cp
    cp._FEE_CACHE.clear()

    # Detection disabled: use explicit defaults
    model = make_ccxt_brokerage(
        "binance",
        product="spot",
        detect_fees=False,
        defaults=(0.0003, 0.0008),
    )
    fee = model.fee_model
    from qmtl.runtime.brokerage.fees import MakerTakerFeeModel

    assert isinstance(fee, MakerTakerFeeModel)
    assert fee.maker_rate == pytest.approx(0.0003)
    assert fee.taker_rate == pytest.approx(0.0008)

    # Detection enabled but ccxt missing → fallback defaults (spot-like)
    model2 = make_ccxt_brokerage("binance", product="spot", detect_fees=True)
    fee2 = model2.fee_model
    assert fee2.maker_rate == pytest.approx(0.0002)
    assert fee2.taker_rate == pytest.approx(0.0007)


def test_fee_detection_cached_load_markets_called_once():
    sys.modules.pop("ccxt", None)
    stub = _install_ccxt_stub(
        markets={"BTC/USDT": {"maker": 0.001, "taker": 0.002}}, trading_fee=(0.0, 0.0)
    )
    from qmtl.runtime.brokerage.ccxt_profile import make_ccxt_brokerage
    import qmtl.runtime.brokerage.ccxt_profile as cp
    cp._FEE_CACHE.clear()

    # First call
    model1 = make_ccxt_brokerage("binance", product="spot", symbol="BTC/USDT")
    # Second call (same key)
    model2 = make_ccxt_brokerage("binance", product="spot", symbol="BTC/USDT")

    # Ensure load_markets was invoked exactly once across both calls
    assert stub._calls["load_markets"] == 1

    # Sanity: both models share the same fee rates
    assert model1.fee_model.maker_rate == model2.fee_model.maker_rate
    assert model1.fee_model.taker_rate == model2.fee_model.taker_rate


def test_enum_and_validation_helper():
    # Install stub to provide .exchanges list for validation
    sys.modules.pop("ccxt", None)
    _install_ccxt_stub(markets={}, trading_fee=(0.001, 0.002))
    from qmtl.runtime.sdk.exchanges import CcxtExchange, ensure_ccxt_exchange

    assert ensure_ccxt_exchange(CcxtExchange.BINANCE) == "binance"
    assert ensure_ccxt_exchange("kraken") == "kraken"
    with pytest.raises(ValueError):
        ensure_ccxt_exchange("not-a-real-exchange")
