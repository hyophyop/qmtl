"""Shared utilities for hazard probability, direction signal, and execution cost."""

from __future__ import annotations

from math import exp, log1p, tanh
from typing import Iterable, Mapping, Sequence


def hazard_probability(
    z: Mapping[str, float],
    beta: Sequence[float],
    feature_keys: Sequence[str],
    *,
    softplus_keys: Iterable[str] = (),
    negative_keys: Iterable[str] = (),
) -> float:
    """Compute logistic hazard probability from feature z-scores.

    Parameters
    ----------
    z:
        Mapping of feature z-scores.
    beta:
        Coefficients ``(beta0, ..., betan)``.
    feature_keys:
        Ordered feature names corresponding to ``beta1..betan``.
    softplus_keys:
        Keys for which to apply a softplus transformation before weighting.
    negative_keys:
        Keys whose contribution is negated.
    """
    x = beta[0]
    for i, key in enumerate(feature_keys, start=1):
        value = z[key]
        if key in softplus_keys:
            value = log1p(exp(value))
        if key in negative_keys:
            value = -value
        x += beta[i] * value
    return 1.0 / (1.0 + exp(-x))


def direction_signal(
    side: int,
    z: Mapping[str, float],
    eta: Sequence[float],
    *,
    weight_aggflow_by_ofi: bool = False,
) -> float:
    """Return side-aware direction gating signal."""
    eta0, eta1, eta2, eta3 = eta
    ofi = z["OFI"]
    micro = z["MicroSlope"]
    agg = z["AggFlow"]
    if weight_aggflow_by_ofi:
        sign_ofi = 1.0 if ofi > 0 else -1.0 if ofi < 0 else 0.0
        agg_term = eta3 * sign_ofi * agg
    else:
        agg_term = eta3 * agg
    x = eta0 + eta1 * ofi + eta2 * micro + agg_term
    return side * tanh(x)


def execution_cost(spread: float, taker_fee: float, impact: float) -> float:
    """Return effective execution cost."""
    return spread / 2 + taker_fee + impact


__all__ = ["hazard_probability", "direction_signal", "execution_cost"]
