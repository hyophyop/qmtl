"""Gap amplification helper transforms."""

# Source: docs/alphadocs/ideas/gpt5pro/gap-amplification-transition-theory.md
# Priority: gpt5pro

from __future__ import annotations

from typing import Iterable, Tuple
import math

from .hazard_utils import hazard_probability as _hazard_probability


def gap_over_depth_sum(
    gaps: Iterable[float],
    depths: Iterable[float],
    lam: float,
    eps: float = 1e-9,
) -> float:
    """Return weighted gap-over-depth sum with exponential decay."""
    total = 0.0
    for k, (gap, depth) in enumerate(zip(gaps, depths)):
        if depth > 0:
            weight = math.exp(-lam * k)
            total += weight * (gap / (depth + eps))
    return total


def hazard_probability(
    ofi: float,
    spread_z: float,
    eta0: float,
    eta1: float,
    eta2: float,
    vol_surprise: float = 0.0,
    cancel_limit_ratio: float = 0.0,
    eta3: float = 0.0,
    eta4: float = 0.0,
) -> float:
    """Logistic hazard combining order flow, spread state and volume signals."""
    z = {
        "OFI": ofi,
        "SpreadZ": spread_z,
        "VolSurprise": vol_surprise,
        "CLR": cancel_limit_ratio,
    }
    beta = (eta0, eta1, eta2, eta3, eta4)
    return _hazard_probability(z, beta, ["OFI", "SpreadZ", "VolSurprise", "CLR"])


def jump_expectation(
    gaps: Iterable[float],
    depths: Iterable[float],
    zeta: float = 0.0,
    microprice_slope: float = 0.0,
) -> float:
    """Estimate expected price jump after queue depletion.

    Parameters
    ----------
    gaps:
        Sequence of price gaps from the best level outward.
    depths:
        Corresponding queue depths. Only the tail of depths is used to
        weight further gap contributions.
    zeta:
        Scaling factor applied to contributions beyond the first level.

    Returns
    -------
    float
        Expected jump size. Defaults to the first gap when ``zeta`` is
        zero or when insufficient data is provided.
    """

    gaps_list = list(gaps)
    depths_list = list(depths)
    if not gaps_list:
        return 1.0

    expect = gaps_list[0]
    if zeta <= 0.0 or len(gaps_list) == 1:
        return expect

    total_depth = sum(depths_list)
    cum_depth = 0.0
    for gap, depth in zip(gaps_list[1:], depths_list[1:]):
        cum_depth += depth
        weight = zeta * (cum_depth / (total_depth + 1e-9))
        expect += weight * gap
    return expect * (1.0 + microprice_slope)


def gati_side(gas: float, hazard: float, jump_expect: float = 1.0) -> float:
    """Return gap amplification transition intensity for one side."""
    return hazard * jump_expect * gas


def filter_ghost_quotes(
    gaps: Iterable[float],
    depths: Iterable[float],
    dwells: Iterable[float],
    tau_min: float,
) -> Tuple[list[float], list[float]]:
    """Remove gap/depth pairs with dwell time below ``tau_min``."""
    fgaps: list[float] = []
    fdepths: list[float] = []
    for gap, depth, dwell in zip(gaps, depths, dwells):
        if dwell >= tau_min:
            fgaps.append(gap)
            fdepths.append(depth)
    return fgaps, fdepths


def cancel_limit_ratio(cancels: float, limits: float, eps: float = 1e-9) -> float:
    """Return cancel-to-limit order ratio."""
    return cancels / (limits + eps)


def microprice_slope(
    best_bid: float,
    best_ask: float,
    bid_depth: float,
    ask_depth: float,
    prev_microprice: float,
    eps: float = 1e-9,
) -> float:
    """Compute slope of microprice relative to previous observation."""
    current = (best_ask * bid_depth + best_bid * ask_depth) / (
        bid_depth + ask_depth + eps
    )
    return current - prev_microprice
