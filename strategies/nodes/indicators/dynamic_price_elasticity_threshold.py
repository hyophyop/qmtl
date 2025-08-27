"""Dynamic Price Elasticity Threshold indicator."""

# Source: docs/alphadocs/ideas/gpt5pro/Dynamic Price Elasticity Threshold Theory.md

TAGS = {
    "scope": "indicator",
    "family": "dynamic_price_elasticity_threshold",
    "interval": "1d",
    "asset": "sample",
}

import math


def dynamic_price_elasticity_threshold_node(data: dict) -> dict:
    """Compute PETI (Price Elasticity Transition Index) and alpha.

    Parameters
    ----------
    data:
        Mapping containing ``delta_q`` (quantity change), ``delta_p`` (price change),
        ``market_depth`` and ``order_imbalance``. Optional keys include
        ``theta1``, ``theta2``, ``gamma`` and ``epsilon``.

    Returns
    -------
    dict
        Mapping with ``peti`` and ``alpha`` entries.
    """

    delta_q = float(data.get("delta_q", 0.0))
    delta_p = float(data.get("delta_p", 0.0))
    depth = float(data.get("market_depth", 0.0))
    order_imbalance = float(data.get("order_imbalance", 0.0))
    theta1 = float(data.get("theta1", 1.0))
    theta2 = float(data.get("theta2", 0.0))
    gamma = float(data.get("gamma", 1.0))
    eps = float(data.get("epsilon", 1e-9))

    peti = 0.0
    if delta_p != 0:
        peti = abs(delta_q / delta_p) / (depth + eps)

    alpha = theta1 * math.exp(peti ** gamma) + theta2 * order_imbalance
    return {"peti": peti, "alpha": alpha}
