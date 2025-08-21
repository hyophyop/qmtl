"""Order book clustering collapse transforms."""

# Source: ../docs/alphadocs/ideas/gpt5pro/order-book-clustering-collapse-theory.md
# Priority: gpt5pro

from __future__ import annotations

from math import exp, log1p, tanh


def _softplus(x: float) -> float:
    """Smooth approximation of max(0, x)."""
    return log1p(exp(x))


def _sigmoid(x: float) -> float:
    """Sigmoid function."""
    return 1.0 / (1.0 + exp(-x))


def hazard_probability(z: dict[str, float], beta: tuple[float, ...]) -> float:
    """Return hazard probability from z-scores.

    Parameters
    ----------
    z: dict[str, float]
        Mapping of feature z-scores such as ``C``, ``Cliff`` and ``Gap``.
    beta: tuple[float, ...]
        Coefficients ``(beta0, ..., beta7)``.
    """
    beta0, beta1, beta2, beta3, beta4, beta5, beta6, beta7 = beta
    x = (
        beta0
        + beta1 * _softplus(z["C"])
        + beta2 * z["Cliff"]
        + beta3 * z["Gap"]
        + beta4 * z["CH"]
        + beta5 * z["RL"]
        - beta6 * z["Shield"]
        + beta7 * z["QDT_inv"]
    )
    return _sigmoid(x)


def direction_gating(side: int, z: dict[str, float], eta: tuple[float, ...]) -> float:
    """Return side-aware direction gating.

    Parameters
    ----------
    side: int
        +1 for ask, -1 for bid.
    z: dict[str, float]
        Mapping of feature z-scores ``OFI``, ``MicroSlope`` and ``AggFlow``.
    eta: tuple[float, ...]
        Coefficients ``(eta0, eta1, eta2, eta3)``.
    """
    eta0, eta1, eta2, eta3 = eta
    x = eta0 + eta1 * z["OFI"] + eta2 * z["MicroSlope"] + eta3 * z["AggFlow"]
    return side * tanh(x)


def execution_cost(spread: float, taker_fee: float, impact: float) -> float:
    """Return effective execution cost."""
    return spread / 2 + taker_fee + impact
