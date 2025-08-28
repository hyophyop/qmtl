"""Execution diffusion–contraction hazard transforms."""

# Source: ../docs/alphadocs/ideas/gpt5pro/Dynamic Execution Diffusion-Contraction Theory.md
# Priority: gpt5pro

from __future__ import annotations

import math
from typing import Sequence


def concentration_scores(
    exec_prices_ticks: Sequence[float],
    exec_sizes: Sequence[float],
    bins: int,
    eps: float = 1e-12,
) -> tuple[float, float, float]:
    """Return entropy, HHI and Fano-based concentration measures."""
    if len(exec_prices_ticks) == 0:
        return 0.0, 0.0, 0.0

    min_p = min(exec_prices_ticks)
    max_p = max(exec_prices_ticks)
    hist = [0.0] * bins
    if max_p - min_p < eps:
        hist[0] = sum(exec_sizes)
    else:
        bin_width = (max_p - min_p) / bins
        for price, size in zip(exec_prices_ticks, exec_sizes):
            idx = min(int((price - min_p) / bin_width), bins - 1)
            hist[idx] += size
    total = sum(hist) + eps
    p = [h / total for h in hist]
    entropy = -sum(pi * math.log(pi + eps) for pi in p if pi > 0)
    hhi = sum(pi * pi for pi in p)
    deltas = [abs(exec_prices_ticks[i] - exec_prices_ticks[i - 1]) for i in range(1, len(exec_prices_ticks))]
    if deltas:
        mean_d = sum(deltas) / len(deltas)
        var_d = sum((d - mean_d) ** 2 for d in deltas) / len(deltas)
        fano = var_d / (mean_d + eps)
    else:
        fano = 0.0
    return entropy, hhi, fano


def path_resistance(depth: Sequence[float] | None, eps: float = 1e-12) -> float:
    """Return negative log cumulative depth as path resistance."""
    if not depth:
        return 0.0
    return -math.log(sum(depth) + eps)


def depth_wedge(
    up_depth: Sequence[float] | None,
    down_depth: Sequence[float] | None,
    eps: float = 1e-12,
) -> float:
    """Return normalized depth wedge between up and down paths."""
    if not up_depth and not down_depth:
        return 0.0
    up = sum(up_depth or [])
    down = sum(down_depth or [])
    return (up - down) / (up + down + eps)


def hazard_probability(x: Sequence[float], eta: Sequence[float]) -> float:
    """Logistic hazard probability with bias term.

    Parameters
    ----------
    x:
        Sequence of input features already standardized.
    eta:
        Coefficients ``[eta0, eta1, ..., etaN]``.
    """
    if not eta:
        return 0.5
    val = eta[0]
    for coeff, xi in zip(eta[1:], x):
        val += coeff * xi
    return 1.0 / (1.0 + math.exp(-val))


def expected_jump(
    gaps_ticks: Sequence[float],
    cum_depth: Sequence[float],
    q_quantile: float,
    zeta: float = 0.5,
) -> float:
    """Return expected jump size based on cumulative depth and gap widths."""
    if not gaps_ticks:
        return 0.0
    pj = []
    for depth in cum_depth:
        pj.append(1.0 if depth <= q_quantile else 0.5)
    jump = gaps_ticks[0]
    for prob, gap in zip(pj[1:], gaps_ticks[1:]):
        jump += zeta * prob * gap
    return jump


def edch_side(prob: float, jump_expect: float) -> float:
    """Return EDCH for one side."""
    return prob * jump_expect


__all__ = [
    "concentration_scores",
    "path_resistance",
    "depth_wedge",
    "hazard_probability",
    "expected_jump",
    "edch_side",
]
