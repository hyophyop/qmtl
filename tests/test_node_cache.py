import pytest
import xarray as xr
from qmtl.sdk import Node, StreamInput, Runner, NodeCache


def test_cache_warmup_and_compute():
    calls = []

    def fn(cache):
        calls.append(cache)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=fn, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "q1", 60, 60, {"v": 1})
    assert node.pre_warmup
    assert node.cache.snapshot()["q1"][60] == [(60, {"v": 1})]
    assert not calls

    Runner.feed_queue_data(node, "q1", 60, 120, {"v": 2})
    assert not node.pre_warmup
    assert node.cache.snapshot()["q1"][60] == [
        (60, {"v": 1}),
        (120, {"v": 2}),
    ]
    assert len(calls) == 1

    Runner.feed_queue_data(node, "q1", 60, 180, {"v": 3})
    assert node.cache.snapshot()["q1"][60] == [
        (120, {"v": 2}),
        (180, {"v": 3}),
    ]
    assert len(calls) == 2


def test_multiple_upstreams():
    calls = []

    def fn(cache):
        calls.append(cache)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=fn, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "u1", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "u2", 60, 60, {"v": 1})
    assert node.pre_warmup
    Runner.feed_queue_data(node, "u1", 60, 120, {"v": 2})
    assert node.pre_warmup
    Runner.feed_queue_data(node, "u2", 60, 120, {"v": 2})
    assert not node.pre_warmup
    assert len(calls) == 1
    snap = node.cache.snapshot()
    assert snap["u1"][60][-1][0] == 120
    assert snap["u2"][60][-1][0] == 120


def test_tensor_memory():
    cache = NodeCache(period=4)
    cache.append("u1", 60, 1, {"v": 1})
    expected = 1 * 1 * 4 * 2 * 8
    assert cache._tensor.nbytes == expected


def test_gap_detection():
    cache = NodeCache(period=2)
    cache.append("u1", 60, 1, {"v": 1})
    assert not cache.missing_flags()["u1"][60]
    cache.append("u1", 60, 3, {"v": 2})
    assert cache.missing_flags()["u1"][60]


def test_on_missing_policy_skip_and_fail():
    calls = []

    def fn(cache):
        calls.append(cache)

    src = StreamInput(interval=60, period=2)
    node = Node(input=src, compute_fn=fn, name="n", interval=60, period=2)

    Runner.feed_queue_data(node, "q1", 60, 1, {"v": 1})
    # Gap -> should skip
    Runner.feed_queue_data(node, "q1", 60, 3, {"v": 2}, on_missing="skip")
    assert node.cache.missing_flags()["q1"][60]
    assert len(calls) == 0

    node2 = Node(input=src, compute_fn=fn, name="n2", interval=60, period=2)
    Runner.feed_queue_data(node2, "q1", 60, 1, {"v": 1})
    with pytest.raises(RuntimeError):
        Runner.feed_queue_data(node2, "q1", 60, 3, {"v": 2}, on_missing="fail")


def test_latest_and_get_slice_list():
    cache = NodeCache(period=3)
    cache.append("u1", 60, 1, {"v": 1})
    assert cache.latest("u1", 60) == (1, {"v": 1})
    cache.append("u1", 60, 2, {"v": 2})
    assert cache.latest("u1", 60) == (2, {"v": 2})

    # Request more items than cached -> only existing returned
    assert cache.get_slice("u1", 60, count=5) == [
        (1, {"v": 1}),
        (2, {"v": 2}),
    ]

    # Unknown upstream -> empty result
    assert cache.latest("unknown", 60) is None
    assert cache.get_slice("unknown", 60, count=2) == []


def test_get_slice_xarray():
    cache = NodeCache(period=4)
    for ts in range(1, 5):
        cache.append("u1", 60, ts, {"v": ts})

    da = cache.get_slice("u1", 60, start=1, end=3)
    assert isinstance(da, xr.DataArray)
    assert da.shape == (2, 2)
    assert list(da[:, 0].astype(int)) == [2, 3]


def test_as_xarray_view_is_read_only_and_matches_snapshot():
    cache = NodeCache(period=2)
    cache.append("u1", 60, 1, {"v": 1})
    cache.append("u1", 60, 2, {"v": 2})

    snap = cache.snapshot()
    da = cache.as_xarray()

    for u in da.coords["u"].values:
        for i in da.coords["i"].values:
            arr = da.sel(u=u, i=i).data
            arr_list = [(int(t), v) for t, v in arr if t is not None]
            assert arr_list == snap[u][i]

    with pytest.raises(ValueError):
        da.data[0, 0, 0, 0] = 99

    assert cache.snapshot() == snap

