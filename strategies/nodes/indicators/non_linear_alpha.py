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

from strategies.utils.cacheview_helpers import fetch_series, latest_value


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

    impact_val = (
        latest_value(view, data.get("impact"))
        if isinstance(data.get("impact"), Node)
        else float(data.get("impact") or 0.0)
    )
    vol_val = (
        latest_value(view, data.get("volatility"))
        if isinstance(data.get("volatility"), Node)
        else float(data.get("volatility") or 0.0)
    )

    obi_deriv = data.get("obi_derivative")
    if isinstance(obi_deriv, Node):
        obi_deriv_val = latest_value(view, obi_deriv)
    else:
        obi_deriv_val = float(obi_deriv) if obi_deriv is not None else None

    if obi_deriv_val is None:
        obi_src = data.get("obi")
        if isinstance(obi_src, Node):
            series = fetch_series(view, obi_src)
            values = series[-2:]
            obi_deriv_val = rate_of_change_series(values) if len(values) == 2 else 0.0
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
