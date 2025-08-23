"""Compute non-linear alpha signal."""

# Source: docs/alphadocs/Kyle-Obizhaeva_non-linear_variation.md

TAGS = {
    "scope": "indicator",
    "family": "non_linear_alpha",
    "interval": "1d",
    "asset": "sample",
}

import math

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node
from qmtl.transforms import rate_of_change_series


def _resolve(value, view: CacheView | None) -> float:
    """Return latest numeric ``value`` from cache if ``value`` is a Node."""

    if isinstance(value, Node):
        if view is None:
            return 0.0
        entries = view[value][value.interval]
        return entries[-1][1] if entries else 0.0
    return float(value or 0.0)


def non_linear_alpha_node(data: dict, view: CacheView | None = None) -> dict:
    """Calculate alpha using impact, volatility, and order book imbalance dynamics.

    Parameters
    ----------
    data:
        Mapping with optional ``impact``, ``volatility``, ``obi_derivative`` or
        ``obi`` entries. Each may be either a numeric value or a :class:`Node`
        whose history can be retrieved from ``view``.
    view:
        Optional cache view supplying historical values for any ``Node`` inputs.
    """

    impact_val = _resolve(data.get("impact"), view)
    vol_val = _resolve(data.get("volatility"), view)

    obi_deriv = data.get("obi_derivative")
    obi_deriv_val = _resolve(obi_deriv, view) if obi_deriv is not None else None

    if obi_deriv_val is None:
        obi_src = data.get("obi")
        if isinstance(obi_src, Node) and view is not None:
            hist = view[obi_src][obi_src.interval][-2:]
            values = [payload for _, payload in hist]
            obi_deriv_val = rate_of_change_series(values)
        else:
            obi_deriv_val = 0.0

    gamma = float(data.get("gamma", 1.0))
    alpha = math.tanh(gamma * impact_val * vol_val) * obi_deriv_val
    return {
        "impact": impact_val,
        "volatility": vol_val,
        "obi_derivative": obi_deriv_val,
        "alpha": alpha,
    }
