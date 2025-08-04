import os
import time
import pytest

from qmtl.sdk import arrow_cache
from importlib import reload

from qmtl.sdk import ProcessingNode, StreamInput

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_arrow_cache_basic():
    cache = arrow_cache.NodeCacheArrow(period=2)
    now = int(time.time())
    cache.append("u1", 60, now, {"v": 1})
    cache.append("u1", 60, now + 60, {"v": 2})
    view = cache.view()
    assert view["u1"][60].latest() == (now + 60 - ((now + 60) % 60), {"v": 2})
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
    now = int(time.time())
    cache.append("u1", 60, now, {"v": 1})
    view = cache.view()
    assert view["u1"][60].latest() == (now - (now % 60), {"v": 1})

    cache.drop_upstream("u1", 60)
    view = cache.view()
    with pytest.raises(KeyError):
        _ = view["u1"][60]

    # second invocation should not raise
    cache.drop_upstream("u1", 60)


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_explicit_eviction_removes_old_entries():
    cache = arrow_cache.NodeCacheArrow(period=2)
    now = int(time.time())
    cache.append("u1", 60, now - 500, {"v": 1})
    cache.evict_expired()
    assert cache.latest("u1", 60) is None


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_access_triggers_eviction(monkeypatch):
    cache = arrow_cache.NodeCacheArrow(period=1)
    now = int(time.time())
    cache.append("u1", 60, now, {"v": 1})
    monkeypatch.setattr(arrow_cache.time, "time", lambda: now + 120)
    assert cache.latest("u1", 60) is None
