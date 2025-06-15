from qmtl.streams import BinanceBTCStream


def test_binance_stream_tags():
    s = BinanceBTCStream(interval=60, period=1)
    assert "binance" in s.tags and "btc" in s.tags

