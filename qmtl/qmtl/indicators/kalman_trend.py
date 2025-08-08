"""Simple Kalman filter trend line."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def kalman_trend(
    source: Node,
    *,
    process_variance: float = 1e-5,
    measurement_variance: float = 1e-2,
    name: str | None = None,
) -> Node:
    """Return a Node computing a Kalman filter smoothed value."""

    def compute(view: CacheView):
        data = [v for _, v in view[source][source.interval]]
        if not data:
            return None
        x = data[0]
        p = 1.0
        for z in data[1:]:
            p += process_variance
            k = p / (p + measurement_variance)
            x = x + k * (z - x)
            p *= 1 - k
        return x

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "kalman_trend",
        interval=source.interval,
        period=source.period,
    )
