"""Gap amplification indicator with hazard-based alpha."""

# Source: docs/alphadocs/ideas/gpt5pro/gap-amplification-transition-theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "gap_amplification",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms.gap_amplification import (
    gap_over_depth_sum,
    gati_side,
    hazard_probability,
)


def _gas(gaps: list[float], depths: list[float], lam: float) -> float:
    """Wrapper for gap amplification score."""
    return gap_over_depth_sum(gaps, depths, lam)


def _hazard(
    ofi: float, spread_z: float, eta0: float, eta1: float, eta2: float
) -> float:
    """Wrapper for hazard probability."""
    return hazard_probability(ofi, spread_z, eta0, eta1, eta2)


def gap_amplification_node(data: dict) -> dict:
    """Compute gap amplification transition alpha.

    Parameters
    ----------
    data:
        Mapping containing either precomputed values or raw inputs:
            ``gas_ask``, ``gas_bid`` and ``hazard``
                Precomputed gap amplification and hazard metrics.
            ``ask_gaps``, ``ask_depths``, ``bid_gaps``, ``bid_depths``, ``lambda``
                Raw inputs for computing ``gas_*`` when precomputed values absent.
            ``ofi``, ``spread_z``, ``eta``
                Raw inputs for computing ``hazard`` when absent.

    Returns
    -------
    dict
        Mapping with ``gati_ask``, ``gati_bid`` and directional ``alpha``.
    """

    gas_ask = data.get("gas_ask")
    gas_bid = data.get("gas_bid")
    hazard = data.get("hazard")

    lam = data.get("lambda", 0.0)

    if gas_ask is None and "ask_gaps" in data and "ask_depths" in data:
        gas_ask = _gas(data["ask_gaps"], data["ask_depths"], lam)
    if gas_bid is None and "bid_gaps" in data and "bid_depths" in data:
        gas_bid = _gas(data["bid_gaps"], data["bid_depths"], lam)

    if hazard is None and {"ofi", "spread_z", "eta"}.issubset(data):
        hazard = _hazard(data["ofi"], data["spread_z"], *data["eta"])

    gas_ask = gas_ask or 0.0
    gas_bid = gas_bid or 0.0
    hazard = hazard or 0.0

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

