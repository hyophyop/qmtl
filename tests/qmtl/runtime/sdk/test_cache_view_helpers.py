from __future__ import annotations

import pytest

from qmtl.runtime.sdk.cache_view import CacheView


def _make_view() -> CacheView:
    return CacheView(
        {
            "prices": {
                60: [
                    (1, {"close": 1.0, "pnl": 0.1}),
                    (2, {"close": 1.2, "pnl": 0.2}),
                ]
            },
            "scalar": {60: [(1, 10.0), (2, 11.0)]},
        }
    )


def test_window_slice_and_frame_columns():
    view = _make_view()

    window = view.window("prices", 60, count=1)
    frame = window.as_frame()

    assert list(frame.columns) == ["ts", "close", "pnl"]
    assert frame.get_column("ts").to_list() == [2]
    assert frame.get_column("close")[0] == pytest.approx(1.2)
    assert window.latest() == {"close": 1.2, "pnl": 0.2}


def test_scalar_payload_frame_and_series():
    view = _make_view()

    window = view.window("scalar", 60)
    frame = window.as_frame()

    assert list(frame.columns) == ["ts", "value"]
    assert frame.get_column("value").to_list() == [10.0, 11.0]

    series = window.to_series("value")
    assert series.to_list() == [10.0, 11.0]


def test_require_columns_and_missing_errors():
    view = _make_view()
    window = view.window("prices", 60)

    window.require_columns(["close"])  # should not raise

    with pytest.raises(ValueError):
        window.require_columns(["close", "missing"])

    with pytest.raises(KeyError):
        window.to_series("missing")


def test_zero_count_returns_empty_frame():
    view = _make_view()
    window = view.window("prices", 60, count=0)

    assert window.as_frame().is_empty()
