import pytest

from qmtl.runtime.sdk.ohlcv_nodeid import build, parse, validate


def test_build_round_trip_and_validate():
    node_id = build("binance", "BTC/USDT", "1m")
    assert node_id == "ohlcv:binance:BTC/USDT:1m"
    parsed = parse(node_id)
    assert parsed == ("binance", "BTC/USDT", "1m")
    validate(node_id)  # should not raise


@pytest.mark.parametrize(
    "bad_timeframe",
    ["", "  ", "2x", "100m"],
)
def test_validate_rejects_unknown_timeframes(bad_timeframe: str):
    node_id = f"ohlcv:binance:BTC/USDT:{bad_timeframe}"
    with pytest.raises(ValueError):
        validate(node_id)


def test_parse_returns_none_for_non_ohlcv_prefix():
    assert parse("trades:binance:BTC/USDT") is None


def test_build_rejects_colon_components():
    with pytest.raises(ValueError):
        build("binance:us", "BTC/USDT", "1m")
    with pytest.raises(ValueError):
        build("binance", "BTC:USDT", "1m")
