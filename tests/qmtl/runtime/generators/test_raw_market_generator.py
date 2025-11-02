from qmtl.runtime.generators.raw_market import RawMarketInput


def test_raw_market_step_keys():
    gen = RawMarketInput(interval=1, period=1, seed=0)
    _, data = gen.step()
    for key in [
        "price",
        "volume",
        "buy_volume",
        "sell_volume",
        "bid_volume",
        "ask_volume",
        "depth_change",
        "impact",
        "spread",
        "taker_fee",
    ]:
        assert key in data
