"""Volume-based features: moving average and standard deviation."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView
from .utils import compute_statistics, create_period_statistics_node


def volume_features(source: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing volume moving average and std over ``period`` values."""
    
    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-period:]]
        if len(values) < period:
            return None
        stats = compute_statistics(values)
        if stats is None:
            return None
        mean, std = stats
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
    return create_period_statistics_node(
        source,
        period,
        stat_type="mean",
        name=name or "avg_volume",
    )


def volume_stats(values: list[float]) -> tuple[float, float]:
    """Return moving average and standard deviation from ``values``."""
    stats = compute_statistics(values)
    if stats is None:
        return 0.0, 0.0
    return stats


__all__ = ["volume_features", "avg_volume_node", "volume_stats"]
