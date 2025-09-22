import pytest

from qmtl.sdk.arrow_cache import ARROW_AVAILABLE, _Slice, _SliceView


@pytest.mark.skipif(not ARROW_AVAILABLE, reason="pyarrow missing")
def test_slice_append_and_latest():
    sl = _Slice(period=3)
    sl.append(10, {"v": 1})
    sl.append(20, {"v": 2})
    sl.append(30, {"v": 3})
    sl.append(40, {"v": 4})

    assert sl.latest() == (40, {"v": 4})
    assert [ts for ts, _ in sl.get_list()] == [20, 30, 40]


@pytest.mark.skipif(not ARROW_AVAILABLE, reason="pyarrow missing")
def test_slice_view_behaviour():
    sl = _Slice(period=4)
    for i in range(4):
        sl.append((i + 1) * 10, {"v": i})

    view = _SliceView(sl)
    assert view[-1] == (40, {"v": 3})
    assert list(view[-2:]) == [(30, {"v": 2}), (40, {"v": 3})]
    sub = view[1:3]
    assert isinstance(sub, _SliceView)
    assert list(sub) == [(20, {"v": 1}), (30, {"v": 2})]
