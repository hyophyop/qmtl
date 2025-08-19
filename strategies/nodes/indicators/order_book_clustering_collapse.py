"""Order book clustering collapse alpha indicator."""

# Source: docs/alphadocs/ideas/gpt5pro/order-book-clustering-collapse-theory.md
# Priority: gpt5pro

from __future__ import annotations

TAGS = {
    "scope": "indicator",
    "family": "order_book_clustering_collapse",
    "interval": "1s",
    "asset": "sample",
}

from math import exp

from qmtl.transforms.order_book_clustering_collapse import (
    hazard_probability,
    direction_gating,
    execution_cost,
)


def _hazard(z: dict[str, float], beta: tuple[float, ...]) -> float:
    """Wrapper for hazard probability."""
    return hazard_probability(z, beta)


def _direction(side: int, z: dict[str, float], eta: tuple[float, ...]) -> float:
    """Wrapper for direction gating."""
    return direction_gating(side, z, eta)


def _cost(spread: float, taker_fee: float, impact: float) -> float:
    """Wrapper for execution cost."""
    return execution_cost(spread, taker_fee, impact)


def order_book_clustering_collapse_node(data: dict) -> dict:
    """Compute order book clustering collapse alpha.

    Parameters
    ----------
    data:
        Mapping containing either precomputed metrics or raw features.
        Expected keys:
            ``hazard_ask``, ``hazard_bid``
                Precomputed hazard probabilities. If missing, supply
                z-score features prefixed with ``ask_`` or ``bid_`` and a
                ``beta`` tuple of coefficients to compute them.
            ``g_ask``, ``g_bid``
                Precomputed direction values. If missing, supply
                side-specific z-scores with ``eta`` coefficients.
            ``pi``
                Fill rate; defaults to ``1.0``.
            ``cost``
                Precomputed cost; if missing, provide ``spread``,
                ``taker_fee`` and ``impact`` components.
            ``gamma``, ``tau``, ``phi``
                Parameters controlling nonlinearity, gating and cost
                penalty. Defaults are ``2.0``, ``0.7`` and ``1.0``.

    Returns
    -------
    dict
        Mapping with intermediate metrics and final ``alpha`` value.
    """

    hazard_ask = data.get("hazard_ask")
    hazard_bid = data.get("hazard_bid")
    g_ask = data.get("g_ask")
    g_bid = data.get("g_bid")

    beta = data.get("beta", (0.0,) * 8)
    eta = data.get("eta", (0.0,) * 4)

    required_hazard_keys = ["C", "Cliff", "Gap", "CH", "RL", "Shield", "QDT_inv"]
    required_direction_keys = ["OFI", "MicroSlope", "AggFlow"]

    if hazard_ask is None and all(f"ask_z_{k}" in data for k in required_hazard_keys):
        z = {k: data[f"ask_z_{k}"] for k in required_hazard_keys}
        hazard_ask = _hazard(z, beta)
    if hazard_bid is None and all(f"bid_z_{k}" in data for k in required_hazard_keys):
        z = {k: data[f"bid_z_{k}"] for k in required_hazard_keys}
        hazard_bid = _hazard(z, beta)

    if g_ask is None and all(f"ask_z_{k}" in data for k in required_direction_keys):
        z = {k: data[f"ask_z_{k}"] for k in required_direction_keys}
        g_ask = _direction(+1, z, eta)
    if g_bid is None and all(f"bid_z_{k}" in data for k in required_direction_keys):
        z = {k: data[f"bid_z_{k}"] for k in required_direction_keys}
        g_bid = _direction(-1, z, eta)

    hazard_ask = hazard_ask or 0.0
    hazard_bid = hazard_bid or 0.0
    g_ask = g_ask or 0.0
    g_bid = g_bid or 0.0

    pi = data.get("pi", 1.0)
    cost = data.get("cost")
    if cost is None:
        spread = data.get("spread", 0.0)
        taker_fee = data.get("taker_fee", 0.0)
        impact = data.get("impact", 0.0)
        cost = _cost(spread, taker_fee, impact)

    gamma = data.get("gamma", 2.0)
    tau = data.get("tau", 0.7)
    phi = data.get("phi", 1.0)

    alpha_ask = max(hazard_ask ** gamma - tau, 0.0) * g_ask
    alpha_bid = max(hazard_bid ** gamma - tau, 0.0) * g_bid
    alpha = (alpha_ask + alpha_bid) * pi * exp(-phi * cost)

    return {
        "hazard_ask": hazard_ask,
        "hazard_bid": hazard_bid,
        "g_ask": g_ask,
        "g_bid": g_bid,
        "pi": pi,
        "cost": cost,
        "alpha": alpha,
    }

