"""Resiliency transform utilities."""

# Source: docs/alphadocs/ideas/resiliency.md

from __future__ import annotations


def impact(volume: float, avg_volume: float, depth: float, beta: float) -> float:
    """Return simple impact measure based on volume and depth."""
    if avg_volume <= 0 or depth <= 0:
        return 0.0
    return beta * (volume / avg_volume) / depth


def resiliency_alpha(
    impact_val: float, volatility: float, obi_derivative: float, gamma: float
) -> float:
    """Compute resiliency alpha from impact and market dynamics."""
    return gamma * impact_val - volatility + obi_derivative

