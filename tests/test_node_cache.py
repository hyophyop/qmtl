import pytest
import pytest
import xarray as xr
from qmtl.sdk import ProcessingNode, StreamInput, Runner, NodeCache


def test_input_window_hash_changes():
    cache = NodeCache(period=2)
    cache.append("u1", 1, 1, {"v": 1})
    h1 = cache.input_window_hash()
    cache.append("u1", 1, 2, {"v": 2})
    h2 = cache.input_window_hash()
    assert h1 != h2


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_cache_warmup_and_compute():
    calls = []

    def fn(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=fn, name="n", interval="60s", period=2)

    Runner.feed_queue_data(node, "q1", 60, 60, {"v": 1})
    assert node.pre_warmup
    assert node.cache.get_slice("q1", 60, count=2) == [(60, {"v": 1})]
    assert not calls

    Runner.feed_queue_data(node, "q1", 60, 120, {"v": 2})
    assert not node.pre_warmup
    assert node.cache.get_slice("q1", 60, count=2) == [
        (60, {"v": 1}),
        (120, {"v": 2}),
    ]
    assert len(calls) == 1

    Runner.feed_queue_data(node, "q1", 60, 180, {"v": 3})
    assert node.cache.get_slice("q1", 60, count=2) == [
        (120, {"v": 2}),
        (180, {"v": 3}),
    ]
    assert len(calls) == 2


def test_node_feed_does_not_execute(monkeypatch):
    monkeypatch.setattr(Runner, "_ray_available", False)

    calls = []

    def fn(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=fn, name="n", interval="60s", period=2)
    node.execute = False

    ready1 = node.feed("q1", 60, 60, {"v": 1})
    ready2 = node.feed("q1", 60, 120, {"v": 2})

    assert not ready1
    assert ready2
    assert len(calls) == 0


def test_multiple_upstreams():
    calls = []

    def fn(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=fn, name="n", interval="60s", period=2)

    Runner.feed_queue_data(node, "u1", 60, 60, {"v": 1})
    Runner.feed_queue_data(node, "u2", 60, 60, {"v": 1})
    assert node.pre_warmup
    Runner.feed_queue_data(node, "u1", 60, 120, {"v": 2})
    assert node.pre_warmup
    Runner.feed_queue_data(node, "u2", 60, 120, {"v": 2})
    assert not node.pre_warmup
    assert len(calls) == 1
    view = node.cache.view()
    assert view["u1"][60].latest()[0] == 120
    assert view["u2"][60].latest()[0] == 120


def test_tensor_memory():
    cache = NodeCache(period=4)
    cache.append("u1", 60, 60, {"v": 1})
    expected = 4 * 2 * 8
    assert cache.resident_bytes == expected


def test_gap_detection():
    cache = NodeCache(period=2)
    cache.append("u1", 60, 1, {"v": 1})
    assert not cache.missing_flags()["u1"][60]
    cache.append("u1", 60, 3, {"v": 2})
    assert cache.missing_flags()["u1"][60]


def test_timestamp_bucket_and_gap_handling():
    cache = NodeCache(period=2)
    cache.append("u1", 60, 102, {"v": 1})
    assert cache.get_slice("u1", 60, count=1) == [(60, {"v": 1})]
    cache.append("u1", 60, 170, {"v": 2})
    assert cache.get_slice("u1", 60, count=2) == [
        (60, {"v": 1}),
        (120, {"v": 2}),
    ]
    assert not cache.missing_flags()["u1"][60]


def test_on_missing_policy_skip_and_fail():
    calls = []

    def fn(view):
        calls.append(view)

    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(input=src, compute_fn=fn, name="n", interval="60s", period=2)

    Runner.feed_queue_data(node, "q1", 60, 1, {"v": 1})
    # Gap -> should skip
    Runner.feed_queue_data(node, "q1", 60, 3, {"v": 2}, on_missing="skip")
    assert node.cache.missing_flags()["q1"][60]
    assert len(calls) == 0

    node2 = ProcessingNode(input=src, compute_fn=fn, name="n2", interval="60s", period=2)
    Runner.feed_queue_data(node2, "q1", 60, 1, {"v": 1})
    with pytest.raises(RuntimeError):
        Runner.feed_queue_data(node2, "q1", 60, 3, {"v": 2}, on_missing="fail")


def test_latest_and_get_slice_list():
    cache = NodeCache(period=3)
    cache.append("u1", 1, 1, {"v": 1})
    assert cache.latest("u1", 1) == (1, {"v": 1})
    cache.append("u1", 1, 2, {"v": 2})
    assert cache.latest("u1", 1) == (2, {"v": 2})

    # Request more items than cached -> only existing returned
    assert cache.get_slice("u1", 1, count=5) == [
        (1, {"v": 1}),
        (2, {"v": 2}),
    ]

    # Unknown upstream -> empty result
    assert cache.latest("unknown", 1) is None
    assert cache.get_slice("unknown", 1, count=2) == []


def test_get_slice_xarray():
    cache = NodeCache(period=4)
    for ts in range(1, 5):
        cache.append("u1", 1, ts, {"v": ts})

    da = cache.get_slice("u1", 1, start=1, end=3)
    assert isinstance(da, xr.DataArray)
    assert da.shape == (2, 2)
    assert list(da[:, 0].astype(int)) == [2, 3]


def test_as_xarray_view_is_read_only_and_matches_get_slice():
    cache = NodeCache(period=2)
    cache.append("u1", 1, 1, {"v": 1})
    cache.append("u1", 1, 2, {"v": 2})

    da = cache.as_xarray()
    expected = {}
    for u in da.coords["u"].values:
        expected[u] = {}
        for i in da.coords["i"].values:
            arr = da.sel(u=u, i=i).data
            arr_list = [(int(t), v) for t, v in arr if t is not None]
            expected[u][i] = arr_list
            assert arr_list == cache.get_slice(u, i, count=cache.period)

    with pytest.raises(ValueError):
        da.data[0, 0, 0, 0] = 99

    for u, mp in expected.items():
        for i, arr_list in mp.items():
            assert cache.get_slice(u, i, count=cache.period) == arr_list


def test_ring_buffer_wraparound():
    cache = NodeCache(period=3)
    cache.append("u1", 1, 1, {"v": 1})
    cache.append("u1", 1, 2, {"v": 2})
    cache.append("u1", 1, 3, {"v": 3})
    cache.append("u1", 1, 4, {"v": 4})

    assert cache.get_slice("u1", 1, count=3) == [
        (2, {"v": 2}),
        (3, {"v": 3}),
        (4, {"v": 4}),
    ]
    assert cache.latest("u1", 1) == (4, {"v": 4})

    cache.append("u1", 1, 5, {"v": 5})

    assert cache.get_slice("u1", 1, count=3) == [
        (3, {"v": 3}),
        (4, {"v": 4}),
        (5, {"v": 5}),
    ]
    assert cache.latest("u1", 1) == (5, {"v": 5})


def test_cache_view_access():
    cache = NodeCache(period=2)
    cache.append("btc_price", 1, 1, {"v": 1})
    cache.append("btc_price", 1, 2, {"v": 2})

    view = cache.view()

    assert view["btc_price"][1].latest() == (2, {"v": 2})
    assert view.btc_price[1].latest() == (2, {"v": 2})

    with pytest.raises(KeyError):
        _ = view["missing"][1]
    with pytest.raises(AttributeError):
        _ = view.missing


def test_cache_view_accepts_node_instance():
    stream = StreamInput(interval="60s", period=2)
    cache = NodeCache(period=2)
    cache.append(stream.node_id, 60, 60, {"v": 1})

    view = cache.view()

    assert view[stream][60].latest() == (60, {"v": 1})


def test_cache_view_access_logging_and_reset():
    cache = NodeCache(period=2)
    cache.append("btc_price", 60, 1, {"v": 1})

    view = cache.view(track_access=True)
    _ = view["btc_price"][60].latest()
    assert view.access_log() == [("btc_price", 60)]

    view2 = cache.view(track_access=True)
    assert view2.access_log() == []
    _ = view2["btc_price"][60]
    assert view2.access_log() == [("btc_price", 60)]


def test_backfill_bulk_merge_and_last_timestamp_update():
    cache = NodeCache(period=4)
    cache.append("u1", 60, 120, {"v": 2})
    cache.append("u1", 60, 180, {"v": 3})

    cache.backfill_bulk(
        "u1",
        60,
        [
            (60, {"v": 1}),
            (120, {"v": "dup"}),
            (240, {"v": 4}),
        ],
    )

    assert cache.get_slice("u1", 60, count=4) == [
        (60, {"v": 1}),
        (120, {"v": 2}),
        (180, {"v": 3}),
        (240, {"v": 4}),
    ]
    assert cache.last_timestamps()["u1"][60] == 240
    assert not cache.missing_flags()["u1"][60]


def test_backfill_bulk_respects_live_append():
    cache = NodeCache(period=3)

    def gen():
        yield (60, {"v": 1})
        cache.append("u1", 60, 120, {"v": "live"})
        yield (120, {"v": "bf"})

    cache.backfill_bulk("u1", 60, gen())

    assert cache.get_slice("u1", 60, count=3) == [
        (60, {"v": 1}),
        (120, {"v": "live"}),
    ]
    assert cache.last_timestamps()["u1"][60] == 120
    assert not cache.missing_flags()["u1"][60]


def test_backfill_state_ranges():
    cache = NodeCache(period=5)
    cache.backfill_bulk(
        "u1",
        60,
        [
            (60, {"v": 1}),
            (120, {"v": 2}),
            (240, {"v": 4}),
        ],
    )
    assert cache.backfill_state.ranges("u1", 60) == [(60, 120), (240, 240)]


def test_backfill_state_merge_multiple_calls():
    cache = NodeCache(period=5)
    cache.backfill_bulk("u1", 60, [(60, {}), (120, {}), (240, {})])
    cache.backfill_bulk("u1", 60, [(180, {}), (300, {})])
    assert cache.backfill_state.ranges("u1", 60) == [(60, 300)]


def test_drop_upstream_removes_data_and_is_idempotent():
    cache = NodeCache(period=2)
    cache.append("u1", 60, 60, {"v": 1})
    assert cache.get_slice("u1", 60, count=1) == [(60, {"v": 1})]

    cache.drop_upstream("u1", 60)
    assert cache.get_slice("u1", 60, count=1) == []
    assert "u1" not in cache.last_timestamps()

    # second invocation should not raise
    cache.drop_upstream("u1", 60)
