"""Return stream payloads as-is."""

from qmtl.runtime.sdk.cache_view import CacheView
import pandas as pd


def identity_transform_node(view: CacheView):
    """Collect payloads from the first bound stream into a DataFrame."""
    stream, intervals = next(iter(view._data.items()))
    interval, window = next(iter(intervals.items()))
    data = [payload for _, payload in window]
    return pd.DataFrame(data)
