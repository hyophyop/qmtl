"""Compute non-linear alpha signal."""

# Source: docs/alphadocs/Kyle-Obizhaeva_non-linear_variation.md

TAGS = {
    "scope": "indicator",
    "family": "non_linear_alpha",
    "interval": "1d",
    "asset": "sample",
}

import math


def non_linear_alpha_node(data):
    """Calculate alpha using impact, volatility, and order book imbalance dynamics."""
    impact = data.get("impact", 0.0)
    volatility = data.get("volatility", 0.0)
    obi_derivative = data.get("obi_derivative", 0.0)
    gamma = data.get("gamma", 1.0)
    alpha = math.tanh(gamma * impact * volatility) * obi_derivative
    return {"alpha": alpha}
