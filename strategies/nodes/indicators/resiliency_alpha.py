"""Resiliency-based alpha indicator."""

# Source: docs/alphadocs/ideas/resiliency.md

TAGS = {
    "scope": "indicator",
    "family": "resiliency_alpha",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms.resiliency import impact, resiliency_alpha


def resiliency_alpha_node(data: dict) -> dict:
    """Compute resiliency impact and alpha signal."""
    volume = data.get("volume", 0.0)
    avg_volume = data.get("avg_volume", 1.0)
    depth = data.get("depth", 1.0)
    volatility = data.get("volatility", 0.0)
    obi_derivative = data.get("obi_derivative", 0.0)
    beta = data.get("beta", 1.0)
    gamma = data.get("gamma", 1.0)

    imp = impact(volume, avg_volume, depth, beta)
    alpha = resiliency_alpha(imp, volatility, obi_derivative, gamma)
    return {"impact": imp, "alpha": alpha}
