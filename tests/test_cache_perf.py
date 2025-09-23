import time
import pytest

from qmtl.runtime.sdk.node import NodeCache
from qmtl.runtime.sdk import arrow_cache


@pytest.mark.skipif(not arrow_cache.ARROW_AVAILABLE, reason="pyarrow missing")
def test_node_vs_arrow_cache_append_performance():
    """Benchmark append throughput of NodeCache vs Arrow cache."""
    n = 10000

    node = NodeCache(period=1024)
    start = time.perf_counter()
    for i in range(n):
        node.append("u1", 60, i * 60, {"v": i})
    node_duration = time.perf_counter() - start

    arr = arrow_cache.NodeCacheArrow(period=1024)
    start = time.perf_counter()
    for i in range(n):
        arr.append("u1", 60, i * 60, {"v": i})
    arrow_duration = time.perf_counter() - start

    node_rate = n / node_duration
    arrow_rate = n / arrow_duration

    # In practice the in-memory cache should handle writes faster
    assert node_rate > arrow_rate

    print(f"NodeCache rate: {node_rate:.1f} ops/s, ArrowCache rate: {arrow_rate:.1f} ops/s")
