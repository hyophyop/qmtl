"""Impact indicator computing liquidity-adjusted market impact."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def impact_node(
    volume: Node,
    avg_volume: Node,
    depth: Node,
    *,
    beta: float = 1.0,
    interval: int | str | None = None,
    name: str | None = None,
) -> Node:
    """Return a node computing liquidity-adjusted market impact.

    The impact is defined as ``sqrt(volume / avg_volume) / (depth ** beta)``
    using the latest values from ``volume``, ``avg_volume`` and ``depth``
    nodes.
    """

    interval = interval or volume.interval

    def compute(view: CacheView):
        vol_data = view[volume][interval]
        avg_data = view[avg_volume][interval]
        depth_data = view[depth][interval]
        if not vol_data or not avg_data or not depth_data:
            return None
        vol = vol_data[-1][1]
        avg = avg_data[-1][1]
        dep = depth_data[-1][1]
        if avg <= 0 or dep <= 0:
            return None
        return (vol / avg) ** 0.5 / (dep ** beta)

    return Node(
        input=(volume, avg_volume, depth),
        compute_fn=compute,
        name=name or "impact",
        interval=interval,
        period=1,
    )
