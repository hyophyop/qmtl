"""Return stream payloads as-is."""

import pandas as pd


def identity_transform_node(view):
    """Collect payloads from the first bound stream into a DataFrame."""
    stream, intervals = next(iter(view.items()))
    interval, window = next(iter(intervals.items()))
    data = [payload for _, payload in window]
    return pd.DataFrame(data)
