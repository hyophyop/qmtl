"""Tactical Liquidity Bifurcation transforms."""

# Source: docs/alphadocs/ideas/gpt5pro/tactical-liquidity-bifurcation-theory.md
# Priority: gpt5pro

from __future__ import annotations

from math import exp, log1p, tanh
from typing import Mapping, Sequence


def _softplus(x: float) -> float:
    """Smooth approximation of ``max(0, x)``."""
    return log1p(exp(x))


def _sigmoid(x: float) -> float:
    """Sigmoid function."""
    return 1.0 / (1.0 + exp(-x))


def bifurcation_hazard(z: Mapping[str, float], beta: Sequence[float]) -> float:
    """Compute hazard probability from feature z-scores.

    Parameters
    ----------
    z:
        Mapping with keys ``SkewDot``, ``CancelDot``, ``Gap``, ``Cliff``,
        ``Shield``, ``QDT_inv`` and ``RequoteLag``.
    beta:
        Coefficients ``(beta0, ..., beta7)`` used in the logistic model.
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


def direction_signal(side: int, z: Mapping[str, float], eta: Sequence[float]) -> float:
    """Return side-aware direction gating signal.

    Parameters
    ----------
    side:
        ``+1`` for ask and ``-1`` for bid.
    z:
        Mapping with keys ``OFI``, ``MicroSlope`` and ``AggFlow``.
    eta:
        Coefficients ``(eta0, eta1, eta2, eta3)``.
    """
    eta0, eta1, eta2, eta3 = eta
    ofi = z["OFI"]
    sign_ofi = 1.0 if ofi > 0 else -1.0 if ofi < 0 else 0.0
    x = eta0 + eta1 * ofi + eta2 * z["MicroSlope"] + eta3 * sign_ofi * z["AggFlow"]
    return side * tanh(x)


def tlbh_alpha(
    hazard: float,
    direction: float,
    pi: float,
    cost: float,
    gamma: float,
    tau: float,
    phi: float,
) -> float:
    """Compute Tactical Liquidity Bifurcation Hazard alpha."""
    return max(hazard**gamma - tau, 0.0) * direction * pi * exp(-phi * cost)
