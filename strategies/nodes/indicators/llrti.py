"""Compute Latent Liquidity Reconfiguration Threshold Index."""

# Source: docs/alphadocs/latent-liquidity-threshold-reconfiguration.md

TAGS = {
    "scope": "indicator",
    "family": "llrti",
    "interval": "1d",
    "asset": "sample",
}


def llrti_node(data: dict) -> dict:
    """Calculate LLRTI from depth changes when price moves beyond a threshold.

    Parameters
    ----------
    data:
        Mapping containing ``depth_changes`` sequence, ``price_change`` value,
        ``delta_t`` interval, and ``delta`` threshold.

    Returns
    -------
    dict
        Mapping with a single key ``"llrti"`` holding the index value.
    """

    price_change = data.get("price_change", 0.0)
    depth_changes = data.get("depth_changes", [])
    delta_t = data.get("delta_t", 1.0)
    delta = data.get("delta", 0.0)

    index = 0.0
    if abs(price_change) > delta and delta_t > 0:
        index = sum(depth_changes) / delta_t
    return {"llrti": index}
