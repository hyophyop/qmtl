"""Tactical Liquidity Bifurcation indicator module."""

# Source: docs/alphadocs/ideas/gpt5pro/tactical-liquidity-bifurcation-theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "tactical_liquidity_bifurcation",
    "interval": "1s",
    "asset": "sample",
}

from typing import Any, Dict, Tuple

from qmtl.transforms.tactical_liquidity_bifurcation import (
    bifurcation_hazard,
    direction_signal,
    tlbh_alpha,
)
from qmtl.transforms.order_book_clustering_collapse import execution_cost


_ComponentKey = Tuple[Any, str, str, str]
_CACHE: Dict[_ComponentKey, float] = {}


def _cache_get(key: _ComponentKey) -> float | None:
    return _CACHE.get(key)


def _cache_set(key: _ComponentKey, value: float) -> None:
    _CACHE[key] = value


def tactical_liquidity_bifurcation_node(data: dict, *, use_cache: bool = True) -> dict:
    """Compute Tactical Liquidity Bifurcation Hazard alpha.

    Parameters
    ----------
    data:
        Mapping containing either precomputed metrics or raw feature z-scores.
        Expected keys:
            ``hazard_ask``, ``hazard_bid``
                Precomputed hazard probabilities. If missing, supply z-score
                features prefixed with ``ask_`` or ``bid_`` and a ``beta``
                tuple of coefficients to compute them.
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
    """

    timestamp = data.get("timestamp")
    hazard_ask = data.get("hazard_ask")
    hazard_bid = data.get("hazard_bid")
    g_ask = data.get("g_ask")
    g_bid = data.get("g_bid")

    if use_cache and timestamp is not None:
        if hazard_ask is None:
            hazard_ask = _cache_get((timestamp, "ask", "risk", "hazard"))
        if hazard_bid is None:
            hazard_bid = _cache_get((timestamp, "bid", "risk", "hazard"))
        if g_ask is None:
            g_ask = _cache_get((timestamp, "ask", "direction", "g"))
        if g_bid is None:
            g_bid = _cache_get((timestamp, "bid", "direction", "g"))

    beta = data.get("beta", (0.0,) * 8)
    eta = data.get("eta", (0.0,) * 4)

    h_keys = ["SkewDot", "CancelDot", "Gap", "Cliff", "Shield", "QDT_inv", "RequoteLag"]
    d_keys = ["OFI", "MicroSlope", "AggFlow"]

    if hazard_ask is None and all(f"ask_z_{k}" in data for k in h_keys):
        z = {k: data[f"ask_z_{k}"] for k in h_keys}
        hazard_ask = bifurcation_hazard(z, beta)
    if hazard_bid is None and all(f"bid_z_{k}" in data for k in h_keys):
        z = {k: data[f"bid_z_{k}"] for k in h_keys}
        hazard_bid = bifurcation_hazard(z, beta)

    if g_ask is None and all(f"ask_z_{k}" in data for k in d_keys):
        z = {k: data[f"ask_z_{k}"] for k in d_keys}
        g_ask = direction_signal(+1, z, eta)
    if g_bid is None and all(f"bid_z_{k}" in data for k in d_keys):
        z = {k: data[f"bid_z_{k}"] for k in d_keys}
        g_bid = direction_signal(-1, z, eta)

    if use_cache and timestamp is not None:
        _cache_set((timestamp, "ask", "risk", "hazard"), hazard_ask or 0.0)
        _cache_set((timestamp, "bid", "risk", "hazard"), hazard_bid or 0.0)
        _cache_set((timestamp, "ask", "direction", "g"), g_ask or 0.0)
        _cache_set((timestamp, "bid", "direction", "g"), g_bid or 0.0)

    hazard_ask = hazard_ask or 0.0
    hazard_bid = hazard_bid or 0.0
    g_ask = g_ask or 0.0
    g_bid = g_bid or 0.0

    pi = data.get("pi", 1.0)
    cost = data.get("cost")
    if use_cache and timestamp is not None and cost is None:
        cost = _cache_get((timestamp, "ask", "cost", "cost"))
    if cost is None:
        spread = data.get("spread", 0.0)
        taker_fee = data.get("taker_fee", 0.0)
        impact = data.get("impact", 0.0)
        cost = execution_cost(spread, taker_fee, impact)
    if use_cache and timestamp is not None:
        _cache_set((timestamp, "ask", "cost", "cost"), cost)
        _cache_set((timestamp, "bid", "cost", "cost"), cost)

    gamma = data.get("gamma", 2.0)
    tau = data.get("tau", 0.7)
    phi = data.get("phi", 1.0)

    alpha_ask = tlbh_alpha(hazard_ask, g_ask, pi, cost, gamma, tau, phi)
    alpha_bid = tlbh_alpha(hazard_bid, g_bid, pi, cost, gamma, tau, phi)
    alpha = alpha_ask + alpha_bid

    return {
        "hazard_ask": hazard_ask,
        "hazard_bid": hazard_bid,
        "g_ask": g_ask,
        "g_bid": g_bid,
        "pi": pi,
        "cost": cost,
        "alpha": alpha,
    }
