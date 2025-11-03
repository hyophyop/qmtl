"""Participation of Volume (POV) indicator."""

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from .helpers import sum_recent_values


def pov(
    executed_volume: Node,
    market_volume: Node,
    *,
    period: int,
    target: float | None = None,
    name: str | None = None,
) -> Node:
    """Return a node computing the Participation of Volume ratio.

    Parameters
    ----------
    executed_volume:
        Node emitting the strategy's executed volume.
    market_volume:
        Node emitting the observed market volume.
    period:
        Number of recent samples used to aggregate volumes.
    target:
        Optional target participation rate. When provided the output includes
        the deviation of the realized participation relative to the target.
    name:
        Optional node name override.
    """

    def compute(view: CacheView):
        exec_sum = sum_recent_values(view, executed_volume, period)
        market_sum = sum_recent_values(view, market_volume, period)

        if exec_sum is None or market_sum is None or market_sum == 0:
            return None

        participation = exec_sum / market_sum
        result = {"participation": participation}
        if target is not None:
            result["target_deviation"] = participation - target
        return result

    return Node(
        input=[executed_volume, market_volume],
        compute_fn=compute,
        name=name or "pov",
        interval=executed_volume.interval,
        period=period,
    )
