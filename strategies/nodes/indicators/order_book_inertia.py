# Source: docs/alphadocs/ideas/gpt5pro/Order Book Inertia Theory.md
"""Order Book Inertia indicator module.

This implementation models per-level quote inertia using survival
probabilities instead of raw stale counts. Hazard z-scores are converted
to survival estimates and normalized by market state variables
(spread, depth and order-flow imbalance) to mitigate endogeneity.
The resulting OBII is combined with queue imbalance to form a
directional alpha. Inputs are cached by timestamp for reuse across
invocations.
"""

from __future__ import annotations

from math import exp
from typing import Sequence

from qmtl.common import FourDimCache

TAGS = {
    "scope": "indicator",
    "family": "order_book_inertia",
    "interval": "1d",
    "asset": "sample",
}

CACHE = FourDimCache()


def order_book_inertia(
    hazard_z: Sequence[float],
    baseline_hazard: Sequence[float],
    weights: Sequence[float],
    spread: float,
    depth: float,
    ofi: float,
) -> float:
    """Return normalized OBII from hazard estimates."""

    hazards = [1.0 / (1.0 + exp(-z)) for z in hazard_z]
    terms = []
    for h, b, w in zip(hazards, baseline_hazard, weights):
        if b >= 1.0:
            continue
        surv_ratio = (1.0 - h) / (1.0 - b) - 1.0
        terms.append(w * surv_ratio)
    raw = sum(terms)
    norm = 1.0 / (1.0 + abs(spread) + depth + abs(ofi))
    return raw * norm


try:  # pragma: no cover - allow tests without qmtl installed
    from qmtl.transforms.order_book_inertia import order_book_inertia as obii_transform
except ModuleNotFoundError:  # pragma: no cover

    def obii_transform(
        hazard_z: Sequence[float],
        baseline_hazard: Sequence[float],
        weights: Sequence[float],
        spread: float,
        depth: float,
        ofi: float,
        bid_volume: float,
        ask_volume: float,
    ):
        obii = order_book_inertia(hazard_z, baseline_hazard, weights, spread, depth, ofi)
        total = bid_volume + ask_volume
        qi = (bid_volume - ask_volume) / total if total != 0 else 0.0
        return obii, qi


def order_book_inertia_node(
    data: dict,
    *,
    baseline_hazard: Sequence[float],
    weights: Sequence[float] | None = None,
    use_cache: bool = True,
    cache: FourDimCache | None = None,
) -> dict:
    """Compute OBII, queue imbalance and directional alpha.

    Parameters
    ----------
    data:
        Mapping with optional keys ``timestamp``, ``hazard_z``, ``spread``,
        ``depth``, ``ofi``, ``bid_volume`` and ``ask_volume``.
    baseline_hazard:
        Sequence of baseline hazard probabilities for each level.
    weights:
        Optional per-level weights; defaults to equal weighting.
    use_cache:
        Whether to read/write intermediate values from ``cache``.
    cache:
        Optional :class:`~qmtl.common.FourDimCache` instance. Defaults to a
        module-level cache.
    """

    cache = cache or CACHE
    ts = data.get("timestamp") if use_cache else None

    def _metric(name: str, default=None):
        val = data.get(name)
        if ts is not None:
            if val is None:
                val = cache.get(ts, "both", 0, name)
            else:
                cache.set(ts, "both", 0, name, val)
        return val if val is not None else default

    hazard_z = _metric("hazard_z", []) or []
    spread = float(_metric("spread", 0.0))
    depth = float(_metric("depth", 0.0))
    ofi = float(_metric("ofi", 0.0))
    bid_vol = float(_metric("bid_volume", 0.0))
    ask_vol = float(_metric("ask_volume", 0.0))

    n = min(len(hazard_z), len(baseline_hazard))
    if weights is None:
        weights = [1.0 / n] * n if n else []
    else:
        weights = list(weights)[:n]

    if n == 0:
        obii = qi = alpha = None
    else:
        obii, qi = obii_transform(
            list(hazard_z)[:n],
            list(baseline_hazard)[:n],
            weights,
            spread,
            depth,
            ofi,
            bid_vol,
            ask_vol,
        )
        alpha = obii * qi

    if ts is not None:
        cache.set(ts, "both", 0, "hazard_z", list(hazard_z))
        cache.set(ts, "both", 0, "spread", spread)
        cache.set(ts, "both", 0, "depth", depth)
        cache.set(ts, "both", 0, "ofi", ofi)
        cache.set(ts, "both", 0, "bid_volume", bid_vol)
        cache.set(ts, "both", 0, "ask_volume", ask_vol)
        cache.set(ts, "both", 0, "obii", obii)
        cache.set(ts, "both", 0, "qi", qi)
        cache.set(ts, "both", 0, "alpha", alpha)

    return {"obii": obii, "qi": qi, "alpha": alpha}
