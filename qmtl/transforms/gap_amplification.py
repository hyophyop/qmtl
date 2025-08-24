"""Gap amplification helper transforms."""

# Source: docs/alphadocs/ideas/gpt5pro/gap-amplification-transition-theory.md
# Priority: gpt5pro

from __future__ import annotations

from typing import Iterable
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
) -> float:
    """Logistic hazard combining order flow and spread state."""
    z = {"OFI": ofi, "SpreadZ": spread_z}
    beta = (eta0, eta1, eta2)
    return _hazard_probability(z, beta, ["OFI", "SpreadZ"])


def jump_expectation(
    gaps: Iterable[float],
    depths: Iterable[float],
    zeta: float = 0.0,
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
    return expect


def gati_side(gas: float, hazard: float, jump_expect: float = 1.0) -> float:
    """Return gap amplification transition intensity for one side."""
    return hazard * jump_expect * gas
