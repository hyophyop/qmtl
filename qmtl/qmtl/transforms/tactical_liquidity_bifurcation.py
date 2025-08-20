# Source: docs/alphadocs/ideas/gpt5pro/tactical-liquidity-bifurcation-theory.md
# Priority: gpt5pro

from __future__ import annotations

from math import exp, log1p, tanh, copysign


def _softplus(x: float) -> float:
    """Smooth approximation of ``max(0, x)``."""
    return log1p(exp(x))


def _sigmoid(x: float) -> float:
    """Sigmoid function."""
    return 1.0 / (1.0 + exp(-x))


def bifurcation_hazard(z: dict[str, float], beta: tuple[float, ...]) -> float:
    """Return bifurcation hazard probability from feature z-scores.

    Parameters
    ----------
    z:
        Mapping with keys ``SkewDot``, ``CancelDot``, ``Gap``, ``Cliff``,
        ``Shield``, ``QDT_inv`` and ``RequoteLag``.
    beta:
        Coefficients ``(beta0, ..., beta7)``.
    """
    (
        beta0,
        beta1,
        beta2,
        beta3,
        beta4,
        beta5,
        beta6,
        beta7,
    ) = beta
    x = (
        beta0
        + beta1 * _softplus(z["SkewDot"])
        + beta2 * _softplus(z["CancelDot"])
        + beta3 * z["Gap"]
        + beta4 * z["Cliff"]
        - beta5 * z["Shield"]
        + beta6 * z["QDT_inv"]
        + beta7 * z["RequoteLag"]
    )
    return _sigmoid(x)


def direction_signal(side: int, z: dict[str, float], eta: tuple[float, ...]) -> float:
    """Return side-aware direction signal.

    Parameters
    ----------
    side:
        +1 for ask, -1 for bid.
    z:
        Mapping with keys ``OFI``, ``MicroSlope`` and ``AggFlow``.
    eta:
        Coefficients ``(eta0, eta1, eta2, eta3)``.
    """
    eta0, eta1, eta2, eta3 = eta
    x = eta0 + eta1 * z["OFI"] + eta2 * z["MicroSlope"] + eta3 * copysign(1.0, z["OFI"]) * z["AggFlow"]
    return side * tanh(x)


def tlbh_alpha(
    hazard: float,
    direction: float,
    fill_rate: float,
    cost: float,
    gamma: float,
    tau: float,
    phi: float,
) -> float:
    """Return Tactical Liquidity Bifurcation Hazard alpha."""
    amp = hazard ** gamma - tau
    if amp <= 0:
        return 0.0
    return amp * direction * fill_rate * exp(-phi * cost)


__all__ = [
    "bifurcation_hazard",
    "direction_signal",
    "tlbh_alpha",
]
