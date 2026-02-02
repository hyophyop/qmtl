"""Return stream payloads as-is."""

from collections.abc import Mapping, Sequence
from typing import Any

from qmtl.runtime.sdk.cache_view import CacheView
import polars as pl


def identity_transform_node(view: CacheView):
    """Collect payloads from the first bound stream into a DataFrame."""
    data = view._data
    if not isinstance(data, Mapping):
        raise TypeError("identity_transform_node expects mapping-backed CacheView")

    stream, intervals = next(iter(data.items()))
    interval_view = intervals._data if isinstance(intervals, CacheView) else intervals
    if not isinstance(interval_view, Mapping):
        raise TypeError(f"Unexpected interval container for stream {stream!r}")

    interval, window = next(iter(interval_view.items()))
    window_data: Any = window._data if isinstance(window, CacheView) else window
    if not isinstance(window_data, Sequence):
        raise TypeError(f"Unexpected window payload for (stream={stream!r}, interval={interval!r})")

    data = [payload for _, payload in window_data]
    return pl.DataFrame(data)
