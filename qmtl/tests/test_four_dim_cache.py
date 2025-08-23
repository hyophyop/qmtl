from qmtl.common import FourDimCache


def test_get_set_and_default():
    cache = FourDimCache()
    cache.set("t1", "ask", 0, "metric", 42)
    assert cache.get("t1", "ask", 0, "metric") == 42
    assert cache.get("t1", "ask", 0, "missing") is None
    assert cache.get("t1", "ask", 0, "missing", 5) == 5


def test_invalidate_dimensions():
    cache = FourDimCache()
    cache.set("t1", "bid", 0, "m1", 1)
    cache.set("t1", "ask", 0, "m1", 2)
    cache.set("t2", "bid", 0, "m1", 3)

    cache.invalidate(side="bid")
    assert cache.get("t1", "bid", 0, "m1") is None
    assert cache.get("t1", "ask", 0, "m1") == 2
    assert cache.get("t2", "bid", 0, "m1") is None

    cache.invalidate()
    assert cache.get("t1", "ask", 0, "m1") is None
