import pytest

from qmtl.runtime.sdk.execution_modeling import MarketData, create_market_data_from_ohlcv


@pytest.mark.parametrize(
    "bid, ask, last, volume, expected_spread, expected_mid, expected_spread_pct",
    [
        pytest.param(99.5, 100.5, 100.0, 10000, 1.0, 100.0, 0.01, id="liquid-market"),
        pytest.param(0.0, 0.0, 0.0, 1000, 0.0, 0.0, 0.0, id="zero-mid-price"),
    ],
)
def test_market_data_properties(bid, ask, last, volume, expected_spread, expected_mid, expected_spread_pct):
    data = MarketData(timestamp=1000, bid=bid, ask=ask, last=last, volume=volume)

    assert data.spread == pytest.approx(expected_spread)
    assert data.mid_price == pytest.approx(expected_mid)
    assert data.spread_pct == pytest.approx(expected_spread_pct)


def test_create_market_data_from_ohlcv():
    data = create_market_data_from_ohlcv(
        timestamp=1000,
        open_price=99.0,
        high=101.0,
        low=98.0,
        close=100.0,
        volume=10000,
        spread_estimate=0.002,
    )

    assert data.timestamp == 1000
    assert data.last == pytest.approx(100.0)
    assert data.volume == 10000
    assert data.bid < data.ask
    assert data.mid_price == pytest.approx(100.0, rel=0.01)
    assert data.spread_pct == pytest.approx(0.002, rel=0.1)
