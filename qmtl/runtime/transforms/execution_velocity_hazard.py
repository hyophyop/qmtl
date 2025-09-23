"""Execution-Driven Velocity Hazard helper transforms."""

# Source: docs/alphadocs/ideas/gpt5pro/Execution-Driven Velocity Hazard.md
# Priority: gpt5pro

from __future__ import annotations

import math
from typing import Iterable, Sequence


def edvh_hazard(
    aevx_ex: float,
    tension: float,
    depth: float,
    ofi: float,
    spread_z: float,
    micro_slope: float,
    eta: Sequence[float],
) -> float:
    """Return logistic hazard probability for one side of EDVH."""
    x = (
        eta[0]
        + eta[1] * aevx_ex
        + eta[2] * tension
        + eta[3] * (-math.log(depth + 1e-9))
        + eta[4] * ofi
        + eta[5] * spread_z
        + eta[6] * micro_slope
    )
    return 1.0 / (1.0 + math.exp(-x))


def expected_jump(
    gaps: Iterable[float],
    cum_depth: Iterable[float],
    q_quantile: float,
    zeta: float = 0.5,
) -> float:
    """Return expected jump size given gaps and cumulative depth."""
    gaps = list(gaps)
    depths = list(cum_depth)
    if not gaps:
        return 0.0
    base = gaps[0]
    tail = 0.0
    for gap, depth in zip(gaps[1:], depths[1:]):
        pj = 1.0 if depth <= q_quantile else 0.5
        tail += pj * gap
    return base + zeta * tail


def execution_velocity_hazard(
    aevx_ex: float,
    tension: float,
    depth: float,
    ofi: float,
    spread_z: float,
    micro_slope: float,
    gaps: Iterable[float],
    cum_depth: Iterable[float],
    eta: Sequence[float],
    q_quantile: float,
    zeta: float = 0.5,
) -> float:
    """Combine hazard and expected jump into an EDVH score."""
    hazard = edvh_hazard(
        aevx_ex, tension, depth, ofi, spread_z, micro_slope, eta
    )
    jump = expected_jump(gaps, cum_depth, q_quantile, zeta)
    return hazard * jump
