"""Calculate market impact factor."""

# Source: docs/alphadocs/Kyle-Obizhaeva_non-linear_variation.md

import math


def impact_node(data):
    """Compute liquidity-adjusted market impact."""
    volume = data.get("volume", 0.0)
    avg_volume = data.get("avg_volume", 1.0)
    depth = data.get("depth", 1.0)
    beta = data.get("beta", 1.0)
    impact = math.sqrt(volume / avg_volume) / (depth ** beta)
    return {"impact": impact}
