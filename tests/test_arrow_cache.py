import time
import pytest

from qmtl.sdk import arrow_cache
from qmtl.sdk.cache_view import CacheView

from qmtl.sdk import ProcessingNode, StreamInput

pytestmark = [
    pytest.mark.filterwarnings('ignore::RuntimeWarning'),
    # Ignore unraisable exception warnings that can be triggered by third-party libs
    pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning'),
]


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_arrow_cache_basic():
    cache = arrow_cache.NodeCacheArrow(period=2)
    cache.append("u1", 60, 60, {"v": 1})
    cache.append("u1", 60, 120, {"v": 2})
    view = cache.view()
    assert view["u1"][60].latest() == (120, {"v": 2})
    assert arrow_cache.pa and isinstance(view["u1"][60].table(), arrow_cache.pa.Table)


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_node_uses_arrow_cache(monkeypatch):
    monkeypatch.setenv("QMTL_ARROW_CACHE", "1")
    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=lambda v: None, name="n", interval="60s", period=2)
    assert isinstance(node.cache, arrow_cache.NodeCacheArrow)
    monkeypatch.delenv("QMTL_ARROW_CACHE", raising=False)


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_drop_upstream_removes_data_and_is_idempotent():
    cache = arrow_cache.NodeCacheArrow(period=2)
    cache.append("u1", 60, 60, {"v": 1})
    view = cache.view()
    assert view["u1"][60].latest() == (60, {"v": 1})

    cache.drop_upstream("u1", 60)
    view = cache.view()
    with pytest.raises(KeyError):
        _ = view["u1"][60]

    # second invocation should not raise
    cache.drop_upstream("u1", 60)


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_no_ray_forces_thread(monkeypatch):
    monkeypatch.setattr(arrow_cache, "RAY_AVAILABLE", True)
    called = {"flag": False}

    def fake_start(self):
        called["flag"] = True

    monkeypatch.setattr(arrow_cache.NodeCacheArrow, "_start_thread_evictor", fake_start)
    import qmtl.sdk.runtime as runtime
    monkeypatch.setattr(runtime, "NO_RAY", True)

    cache = arrow_cache.NodeCacheArrow(period=2)
    assert called["flag"]


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_arrow_cache_view_sequence_behavior():
    cache = arrow_cache.NodeCacheArrow(period=4)
    for i in range(4):
        cache.append("u", 60, (i + 1) * 60, i)
    view = cache.view()
    seq = view["u"][60]
    assert seq[-1] == (240, 3)
    assert list(seq[-2:]) == [(180, 2), (240, 3)]
    assert not seq[:0]


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_arrow_cache_view_iteration_benchmark():
    cache = arrow_cache.NodeCacheArrow(period=1024)
    n = 5000
    for i in range(n):
        cache.append("u", 60, (i + 1) * 60, {"v": i})

    start = time.perf_counter()
    view = cache.view()
    total = sum(v["v"] for _, v in view["u"][60])
    arrow_duration = time.perf_counter() - start

    sl = cache._slices[("u", 60)]
    start = time.perf_counter()
    data = {"u": {60: sl.get_list()}}
    list_view = CacheView(data)
    total2 = sum(v["v"] for _, v in list_view["u"][60])
    list_duration = time.perf_counter() - start

    assert total == total2
    assert arrow_duration < list_duration
