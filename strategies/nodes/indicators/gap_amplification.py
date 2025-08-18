"""Gap amplification indicator with hazard-based alpha."""

# Source: docs/alphadocs/ideas/gpt5pro/gap-amplification-transition-theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "gap_amplification",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms.gap_amplification import gati_side


def gap_amplification_node(data: dict) -> dict:
    """Compute gap amplification transition alpha.

    Parameters
    ----------
    data:
        Mapping containing:
            ``gas_ask``: ask-side gap amplification score.
            ``gas_bid``: bid-side gap amplification score.
            ``hazard``: hazard probability.

    Returns
    -------
    dict
        Mapping with ``gati_ask``, ``gati_bid`` and directional ``alpha``.
    """

    gas_ask = data.get("gas_ask", 0.0)
    gas_bid = data.get("gas_bid", 0.0)
    hazard = data.get("hazard", 0.0)

    gati_ask = gati_side(gas_ask, hazard)
    gati_bid = gati_side(gas_bid, hazard)
    alpha = gati_bid - gati_ask

    return {
        "gas_ask": gas_ask,
        "gas_bid": gas_bid,
        "gati_ask": gati_ask,
        "gati_bid": gati_bid,
        "hazard": hazard,
        "alpha": alpha,
    }

