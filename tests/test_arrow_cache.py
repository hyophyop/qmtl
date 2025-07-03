import os
import pytest

from qmtl.sdk import arrow_cache
from importlib import reload

from qmtl.sdk import ProcessingNode, StreamInput

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')


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
