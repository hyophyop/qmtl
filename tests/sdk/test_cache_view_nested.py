import pytest

from qmtl.sdk.cache_view import CacheView


def test_attr_access_for_mapping_key():
    data = {"foo": {1: [(0, "x")]}}
    view = CacheView(data)
    # Attribute maps to key lookup; nested index resolves to tuple
    last = view.foo[1][-1]
    assert last == (0, "x")


def test_nested_cacheview_is_unwrapped():
    inner = CacheView({"bar": {2: [(1, "v")]}})
    outer = CacheView({"foo": inner})
    # Accessing outer.foo should unwrap the inner CacheView
    seq = outer.foo.bar[2]
    assert seq[-1] == (1, "v")


def test_track_access_logs_once():
    data = {"u": {1: [(1, 10)]}}
    view = CacheView(data, track_access=True)
    _ = view.u[1]
    assert view.access_log() == [("u", 1)]
