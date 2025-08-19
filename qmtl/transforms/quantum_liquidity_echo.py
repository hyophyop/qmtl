"""Quantum liquidity echo helper transforms."""

from __future__ import annotations

import math
from typing import Iterable, Tuple


def accumulate_echo(alphas: Iterable[float], delta_t: float, tau: float) -> float:
    """Return exponentially decayed sum of past alphas."""
    echo = 0.0
    for k, alpha in enumerate(alphas, start=1):
        echo += alpha * math.exp(-k * delta_t / tau)
    return echo


def amplification_index(echo: float, sigma: float) -> float:
    """Return amplification index given echo amplitude and volatility."""
    return echo ** 2 / sigma if sigma != 0 else 0.0


def decide_action(echo: float, qe: float, threshold: float) -> int:
    """Return action based on amplification index threshold."""
    if qe > threshold and echo != 0:
        return -1 if echo > 0 else 1
    return 0


def quantum_liquidity_echo(
    alphas: Iterable[float],
    delta_t: float,
    tau: float,
    sigma: float,
    threshold: float,
) -> Tuple[float, float, int]:
    """Return echo amplitude, amplification index and action."""
    echo = accumulate_echo(alphas, delta_t, tau)
    qe = amplification_index(echo, sigma)
    action = decide_action(echo, qe, threshold)
    return echo, qe, action


__all__ = [
    "accumulate_echo",
    "amplification_index",
    "decide_action",
    "quantum_liquidity_echo",
]
