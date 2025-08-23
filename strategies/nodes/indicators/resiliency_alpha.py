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

from typing import Hashable

from qmtl.transforms.resiliency import impact, resiliency_alpha

TAGS = {
    "scope": "indicator",
    "family": "resiliency_alpha",
    "interval": "1d",
    "asset": "sample",
}


# Cache for time-series inputs. Keys are ``(timestamp, side, level, metric)``
# tuples as documented above.
_INPUT_CACHE: dict[tuple[Hashable, str, int, str], float] = {}


def resiliency_alpha_node(data: dict) -> dict:
    """Compute resiliency impact and alpha signal.

    Parameters
    ----------
    data:
        Mapping of input parameters. ``timestamp``, ``side`` and ``level``
        identify cache entries. Metrics may be omitted to reuse cached values.
    """

    ts = data.get("timestamp")
    side = data.get("side", "unknown")
    level = int(data.get("level", 0))

    def _metric(name: str, default: float) -> float:
        key = (ts, side, level, name)
        if name in data and data[name] is not None:
            val = float(data[name])
        else:
            val = _INPUT_CACHE.get(key, default)
        _INPUT_CACHE[key] = val
        return val

    volume = _metric("volume", 0.0)
    avg_volume = _metric("avg_volume", 1.0)
    depth = _metric("depth", 1.0)
    volatility = _metric("volatility", 0.0)
    obi_derivative = data.get("obi_derivative", 0.0)
    beta = data.get("beta", 1.0)
    gamma = data.get("gamma", 1.0)

    imp = impact(volume, avg_volume, depth, beta)
    alpha = resiliency_alpha(imp, volatility, obi_derivative, gamma)
    return {"impact": imp, "alpha": alpha}
