"""Simple square-root market impact helper."""

import math


def impact(Q: float, V: float, depth: float, beta: float) -> float:
    """Return market impact as ``sqrt(Q/V) / depth**beta``.

    Parameters
    ----------
    Q:
        Trade volume.
    V:
        Average volume.
    depth:
        Order book depth.
    beta:
        Depth decay exponent.
    """
    if V <= 0 or depth <= 0:
        return 0.0
    return math.sqrt(Q / V) / depth**beta


__all__ = ["impact"]
