from qmtl.sdk.generators import GarchInput, HestonInput, RoughBergomiInput


def _test_stream(cls):
    stream = cls(interval=1, period=2, seed=42)
    data = stream.generate(5)
    assert len(data) == 5
    assert all(ts == i + 1 for i, (ts, _) in enumerate(data))
    assert all("price" in payload for _, payload in data)


def test_garch_input():
    _test_stream(GarchInput)


def test_heston_input():
    _test_stream(HestonInput)


def test_rough_bergomi_input():
    _test_stream(RoughBergomiInput)

