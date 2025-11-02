"""Resiliency transform utilities."""

# Source: ../docs/alphadocs/ideas/resiliency.md

from __future__ import annotations

import math


def impact(volume: float, avg_volume: float, depth: float, beta: float) -> float:
    """Return impact measure using volume, depth and non-linear scaling."""
    if avg_volume <= 0 or depth <= 0:
        return 0.0
    return math.sqrt(volume / avg_volume) / (depth ** beta)


def resiliency_alpha(
    impact_val: float, volatility: float, obi_derivative: float, gamma: float
) -> float:
    """Compute resiliency alpha from impact and market dynamics."""
    return math.tanh(gamma * impact_val * volatility) * obi_derivative

