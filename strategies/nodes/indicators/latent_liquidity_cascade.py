"""Estimate latent liquidity cascade via resiliency gap.

Compute a normalized deficit of limit order resiliency. The resiliency gap is
measured as net limit order flow (adds - cancels - market orders). When this
net flow is negative, its magnitude relative to visible depth indicates
structural liquidity stress.
"""

# Source: docs/alphadocs/ideas/gpt5pro/Latent Liquidity Cascade Theory.md

TAGS = {
    "scope": "indicator",
    "family": "latent_liquidity_cascade",
    "interval": "1s",
    "asset": "sample",
}


def latent_liquidity_cascade_node(data: dict) -> dict:
    """Compute resiliency gap and normalized alpha.

    Parameters
    ----------
    data:
        Mapping with ``limit_additions``, ``cancels``, ``market_orders`` and
        optional ``depth``.
    """
    limit_additions = float(data.get("limit_additions", 0.0))
    cancels = float(data.get("cancels", 0.0))
    market_orders = float(data.get("market_orders", 0.0))
    depth = float(data.get("depth", 1.0)) or 1.0

    net_flow = limit_additions - cancels - market_orders
    gap = -net_flow if net_flow < 0 else 0.0
    alpha = gap / depth

    return {
        "net_flow": net_flow,
        "resiliency_gap": gap,
        "alpha": alpha,
    }
