"""Compute LLRTI baseline from GPT-5-Pro: sum depth change rate when |ΔP| > δ."""
# Source: docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "llrti",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms import llrti


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

    index = llrti(
        data.get("depth_changes", []),
        data.get("price_change", 0.0),
        data.get("delta_t", 1.0),
        data.get("delta", 0.0),
    )
    return {"llrti": index}
