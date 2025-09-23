"""Volume-based features: moving average and standard deviation."""

import math

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def volume_features(source: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing volume moving average and std over ``period`` values."""

    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-period:]]
        if len(values) < period:
            return None
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        return {"volume_hat": mean, "volume_std": std}

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "volume_features",
        interval=source.interval,
        period=period,
    )


def avg_volume_node(source: Node, period: int, *, name: str | None = None) -> Node:
    """Return a node computing the moving average of volume over ``period``.

    Parameters
    ----------
    source:
        Node emitting volume values.
    period:
        Number of recent observations to average.
    name:
        Optional node name. Defaults to ``"avg_volume"``.

    Returns
    -------
    Node
        Node producing the mean of the last ``period`` volume samples.
    """

    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-period:]]
        if len(values) < period:
            return None
        return sum(values) / len(values)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "avg_volume",
        interval=source.interval,
        period=period,
    )


def volume_stats(values: list[float]) -> tuple[float, float]:
    """Return moving average and standard deviation from ``values``."""
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, math.sqrt(variance)


__all__ = ["volume_features", "avg_volume_node", "volume_stats"]
