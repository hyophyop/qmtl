"""Gap amplification indicator with hazard-based alpha."""

# Source: docs/alphadocs/ideas/gpt5pro/gap-amplification-transition-theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "gap_amplification",
    "interval": "1d",
    "asset": "sample",
}

import math
from typing import Iterable


def _gas(gaps: Iterable[float], depths: Iterable[float], lam: float, eps: float = 1e-9) -> float:
    """Return weighted gap-over-depth sum with exponential decay."""
    gas = 0.0
    for k, (gap, depth) in enumerate(zip(gaps, depths)):
        if depth > 0:
            weight = math.exp(-lam * k)
            gas += weight * (gap / (depth + eps))
    return gas


def _hazard(ofi: float, spread_z: float, eta0: float, eta1: float, eta2: float) -> float:
    """Logistic hazard combining order flow and spread state."""
    x = eta0 + eta1 * ofi + eta2 * spread_z
    return 1.0 / (1.0 + math.exp(-x))


def gap_amplification_node(data: dict) -> dict:
    """Compute gap amplification transition alpha.

    Parameters
    ----------
    data:
        Mapping containing:
            ``ask_gaps``: sequence of ask-side gaps.
            ``ask_depths``: sequence of ask-side depths.
            ``bid_gaps``: sequence of bid-side gaps.
            ``bid_depths``: sequence of bid-side depths.
            ``lambda``: exponential decay for gap weights.
            ``ofi``: order flow imbalance.
            ``spread_z``: spread z-score.
            ``eta``: logistic parameters ``(eta0, eta1, eta2)``.

    Returns
    -------
    dict
        Mapping with ``gati_ask``, ``gati_bid`` and directional ``alpha``.
    """

    ask_gaps = data.get("ask_gaps", [])
    ask_depths = data.get("ask_depths", [])
    bid_gaps = data.get("bid_gaps", [])
    bid_depths = data.get("bid_depths", [])
    lam = data.get("lambda", 0.5)
    ofi = data.get("ofi", 0.0)
    spread_z = data.get("spread_z", 0.0)
    eta0, eta1, eta2 = data.get("eta", (0.0, 0.0, 0.0))

    gas_ask = _gas(ask_gaps, ask_depths, lam)
    gas_bid = _gas(bid_gaps, bid_depths, lam)
    hazard = _hazard(ofi, spread_z, eta0, eta1, eta2)

    gati_ask = gas_ask * hazard
    gati_bid = gas_bid * hazard
    alpha = gati_bid - gati_ask

    return {
        "gas_ask": gas_ask,
        "gas_bid": gas_bid,
        "gati_ask": gati_ask,
        "gati_bid": gati_bid,
        "hazard": hazard,
        "alpha": alpha,
    }

