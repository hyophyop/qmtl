"""Gap amplification helper transforms."""

from __future__ import annotations

from typing import Iterable
import math


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
    x = eta0 + eta1 * ofi + eta2 * spread_z
    return 1.0 / (1.0 + math.exp(-x))


def gati_side(gas: float, hazard: float, jump_expect: float = 1.0) -> float:
    """Return gap amplification transition intensity for one side."""
    return hazard * jump_expect * gas
