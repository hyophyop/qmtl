import polars as pl
import pytest

from qmtl.runtime.sdk.cache_view import CacheView


def test_window_and_as_frame_single_node():
    view = CacheView({"a": {1: [(1, {"price": 1}), (2, {"price": 2}), (3, {"price": 3})]}})

    window = view.window("a", 1, 2)
    assert window == [(2, {"price": 2}), (3, {"price": 3})]

    frame = view.as_frame("a", 1, window=2, columns=["price"])
    assert frame.frame.get_column("t").to_list() == [2, 3]
    assert frame.frame.get_column("price").to_list() == [2, 3]
    assert pytest.approx(frame.returns().to_list()) == [0.5]


def test_as_frame_accepts_polars_series_cache_leaf():
    series = pl.Series([(1, {"price": 1}), (2, {"price": 2})], dtype=pl.Object)
    view = CacheView({"a": {1: series}})

    frame = view.as_frame("a", 1)

    assert frame.frame.get_column("t").to_list() == [1, 2]
    assert frame.frame.get_column("price").to_list() == [1, 2]


def test_align_frames_with_shared_timestamps():
    view = CacheView(
        {
            "a": {1: [(1, 1), (2, 2), (3, 3)]},
            "b": {1: [(2, 20), (3, 30), (4, 40)]},
        }
    )

    aligned = view.align_frames([("a", 1), ("b", 1)])
    assert len(aligned) == 2

    left, right = aligned
    assert left.frame.get_column("t").to_list() == [2, 3]
    assert left.frame.get_column("value").to_list() == [2, 3]
    assert right.frame.get_column("value").to_list() == [20, 30]


def test_missing_columns_raise():
    view = CacheView({"a": {1: [(1, {"price": 1})]}})

    frame = view.as_frame("a", 1, columns=["price"])
    frame.validate_columns(["price"])

    with pytest.raises(KeyError):
        view.as_frame("a", 1, columns=["price", "volume"])

    with pytest.raises(KeyError):
        frame.validate_columns(["volume"])


def test_track_access_and_pct_change():
    view = CacheView({"a": {1: [(1, 1), (2, 2), (3, 4)]}}, track_access=True)

    frame = view.as_frame("a", 1, window=3)
    assert view.access_log() == [("a", 1)]

    pct = frame.pct_change(window=2)
    assert isinstance(pct, pl.Series)
    assert pct.to_list() == [3.0]


def test_compute_fn_end_to_end_alignment():
    view = CacheView(
        {
            "price": {60: [(1, {"close": 100}), (2, {"close": 102}), (3, {"close": 104})]},
            "signal": {60: [(1, {"flag": 0}), (2, {"flag": 1}), (3, {"flag": 1})]},
        }
    )

    def compute(cache_view: CacheView) -> pl.DataFrame:
        price_frame, signal_frame = cache_view.align_frames([("price", 60), ("signal", 60)], window=3)

        returns = price_frame.validate_columns(["close"]).returns(window=1, dropna=False)
        flags = signal_frame.validate_columns(["flag"]).frame.get_column("flag")
        t_col = price_frame.frame.get_column("t")
        return pl.DataFrame(
            {
                "t": t_col,
                "close_return": returns,
                "flag": flags,
            }
        )

    result = compute(view)

    assert result.get_column("t").to_list() == [1, 2, 3]
    assert result.get_column("flag").to_list() == [0, 1, 1]
    close_returns = result.get_column("close_return").to_list()
    assert close_returns[0] is None
    assert pytest.approx(close_returns[-1]) == 0.0196078431372549
