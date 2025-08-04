"""Angle transformation node expressing trend slope as an angle."""

import math

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def angle(
    source: Node,
    period: int,
    *,
    radians: bool = False,
    name: str | None = None,
) -> Node:
    """Return a Node computing the slope angle over ``period`` values."""

    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-period:]]
        if len(values) < 2:
            return None
        n = len(values)
        x = range(n)
        mean_x = sum(x) / n
        mean_y = sum(values) / n
        numer = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, values))
        denom = sum((xi - mean_x) ** 2 for xi in x)
        if denom == 0:
            slope = 0.0
        else:
            slope = numer / denom
        ang = math.atan(slope)
        if not radians:
            ang = math.degrees(ang)
        return ang

    return Node(
        input=source,
        compute_fn=compute,
        name=name or ("angle_rad" if radians else "angle"),
        interval=source.interval,
        period=period,
    )
