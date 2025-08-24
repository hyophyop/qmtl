"""Compute non-linear alpha signal.

If ``impact`` is omitted, it is derived from trade inputs ``Q`` (volume),
``V`` (average volume), ``depth`` and ``beta`` via
``sqrt(Q / V) / depth**beta``.
"""

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
from qmtl.transforms.impact import impact as compute_impact

from strategies.utils.cacheview_helpers import fetch_series, latest_value


def non_linear_alpha_node(data: dict, view: CacheView | None = None) -> dict:
    """Calculate alpha using impact, volatility, and order book imbalance dynamics.

    Parameters
    ----------
    data:
        Mapping with optional ``impact``, ``volatility``, ``obi_derivative`` or
        ``obi`` entries. ``impact`` may be omitted if ``Q``, ``V``, ``depth`` and
        ``beta`` are provided for automatic derivation. Each entry can be a
        numeric value or a :class:`Node` whose history can be retrieved from
        ``view``.
    view:
        Optional cache view supplying historical values for any ``Node`` inputs.
    """

    def _resolve(val):
        return latest_value(view, val, default=None) if isinstance(val, Node) else val

    imp_src = data.get("impact")
    if imp_src is not None:
        impact_val = float(_resolve(imp_src) or 0.0)
    else:
        Q = _resolve(data.get("Q"))
        V = _resolve(data.get("V"))
        depth = _resolve(data.get("depth"))
        beta = float(data.get("beta", 1.0))
        if None not in (Q, V, depth):
            impact_val = compute_impact(float(Q), float(V), float(depth), beta)
        else:
            impact_val = 0.0
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
