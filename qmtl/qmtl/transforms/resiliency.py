"""Resiliency impact and alpha transforms."""

# Source: docs/alphadocs/ideas/resiliency.md

import math


def impact(volume: float, avg_volume: float, depth: float, beta: float) -> float:
    """Return market impact estimate.

    Parameters
    ----------
    volume:
        Current traded volume ``Q_t``.
    avg_volume:
        Average volume ``V_t`` used for normalization.
    depth:
        Aggregated order book depth ``Depth_t``.
    beta:
        Liquidity sensitivity exponent ``β``.

    Returns
    -------
    float
        Impact value. Returns ``0.0`` when ``avg_volume`` or ``depth`` is
        non-positive.
    """
    if avg_volume <= 0 or depth <= 0:
        return 0.0
    return math.sqrt(volume / avg_volume) / (depth ** beta)


def resiliency_alpha(
    impact: float,
    volatility: float,
    obi_derivative: float,
    gamma: float,
) -> float:
    """Return alpha from impact, volatility and OBI derivative."""
    return math.tanh(gamma * impact * volatility) * obi_derivative


__all__ = ["impact", "resiliency_alpha"]

