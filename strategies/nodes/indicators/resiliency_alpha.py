"""Resiliency-based alpha indicator.

Cache Key Scheme
----------------
Inputs are cached using ``(timestamp, side, level, metric)`` tuples where
``metric`` is one of ``volume``, ``avg_volume``, ``depth`` or ``volatility``.
Cached values are reused when the corresponding metric is omitted on
subsequent invocations.
"""

# Source: docs/alphadocs/ideas/resiliency.md

from __future__ import annotations

from qmtl.transforms.resiliency import impact, resiliency_alpha

from qmtl.common import FourDimCache

TAGS = {
    "scope": "indicator",
    "family": "resiliency_alpha",
    "interval": "1d",
    "asset": "sample",
}


# Cache for time-series inputs shared across invocations.
CACHE = FourDimCache()


def resiliency_alpha_node(data: dict) -> dict:
    """Compute resiliency impact and alpha signal.

    Parameters
    ----------
    data:
        Mapping of input parameters. ``timestamp``, ``side`` and ``level``
        identify cache entries. Metrics may be omitted to reuse cached values.

    Notes
    -----
    The alpha is bounded by the ``obi_derivative`` magnitude via a ``tanh``
    transform applied to ``impact`` and ``volatility``.
    """

    ts = data.get("timestamp")
    side = data.get("side", "unknown")
    level = int(data.get("level", 0))

    def _metric(name: str, default: float) -> float:
        val = data.get(name)
        if val is None:
            val = CACHE.get(ts, side, level, name, default)
        val = float(val)
        CACHE.set(ts, side, level, name, val)
        return val

    volume = _metric("volume", 0.0)
    avg_volume = _metric("avg_volume", 1.0)
    depth = _metric("depth", 1.0)
    volatility = _metric("volatility", 0.0)
    obi_derivative = data.get("obi_derivative", 0.0)
    beta = data.get("beta", 1.0)
    gamma = data.get("gamma", 1.0)

    impact_val = impact(volume, avg_volume, depth, beta)
    alpha = resiliency_alpha(impact_val, volatility, obi_derivative, gamma)
    return {"impact": impact_val, "alpha": alpha}
