import pandas as pd
import pytest

from qmtl.runtime.sdk.cache_view import CacheView


def test_window_and_as_frame_single_node():
    view = CacheView({"a": {1: [(1, {"price": 1}), (2, {"price": 2}), (3, {"price": 3})]}})

    window = view.window("a", 1, 2)
    assert window == [(2, {"price": 2}), (3, {"price": 3})]

    frame = view.as_frame("a", 1, window=2, columns=["price"])
    assert list(frame.frame.index) == [2, 3]
    assert frame.frame["price"].tolist() == [2, 3]
    assert pytest.approx(frame.returns().tolist()) == [0.5]


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
    assert list(left.frame.index) == [2, 3]
    assert left.frame["value"].tolist() == [2, 3]
    assert right.frame["value"].tolist() == [20, 30]


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
    assert isinstance(pct, pd.Series)
    assert pct.tolist() == [3.0]


def test_compute_fn_end_to_end_alignment():
    view = CacheView(
        {
            "price": {60: [(1, {"close": 100}), (2, {"close": 102}), (3, {"close": 104})]},
            "signal": {60: [(1, {"flag": 0}), (2, {"flag": 1}), (3, {"flag": 1})]},
        }
    )

    def compute(cache_view: CacheView) -> pd.DataFrame:
        price_frame, signal_frame = cache_view.align_frames([("price", 60), ("signal", 60)], window=3)

        returns = price_frame.validate_columns(["close"]).returns(window=1, dropna=False)
        flags = signal_frame.validate_columns(["flag"]).frame["flag"]

        return returns.to_frame("close_return").assign(flag=flags.values)

    result = compute(view)

    assert list(result.index) == [1, 2, 3]
    assert result["flag"].tolist() == [0, 1, 1]
    assert pd.isna(result["close_return"].iloc[0])
    assert pytest.approx(result["close_return"].iloc[-1]) == 0.0196078431372549
