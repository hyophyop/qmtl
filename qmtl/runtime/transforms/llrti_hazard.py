"""LLRTI hazard transform combining index and jump probability."""
# Source: docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md
# Priority: gpt5pro

from __future__ import annotations

from math import exp
from typing import Iterable, Mapping, Sequence

from .llrti import llrti
from .hazard_utils import hazard_probability, execution_cost


def label_jumps(price_changes: Iterable[float], threshold: float) -> list[int]:
    """Return binary jump labels for ``price_changes`` given ``threshold``."""
    return [1 if abs(pc) >= threshold else 0 for pc in price_changes]


def fit_llrti_jump_model(
    features: Iterable[Mapping[str, float]],
    jump_labels: Iterable[int],
    feature_keys: Sequence[str],
    lr: float = 0.1,
    epochs: int = 100,
) -> Sequence[float]:
    """Estimate logistic regression coefficients for jump probability.

    Parameters
    ----------
    features:
        Sequence of feature mappings (e.g., LLRTI and state variables).
    jump_labels:
        Corresponding binary labels indicating whether a jump occurred.
    feature_keys:
        Ordered keys from ``features`` used as predictors.
    lr:
        Gradient descent learning rate.
    epochs:
        Number of training iterations.
    """
    x = list(features)
    y = list(jump_labels)
    if len(x) != len(y):
        raise ValueError("Mismatched feature and label lengths")
    beta = [0.0] * (len(feature_keys) + 1)
    n = len(x)
    for _ in range(epochs):
        grads = [0.0] * len(beta)
        for z, yi in zip(x, y):
            linear = beta[0]
            for i, key in enumerate(feature_keys, start=1):
                linear += beta[i] * z[key]
            p = 1.0 / (1.0 + exp(-linear))
            diff = p - yi
            grads[0] += diff
            for i, key in enumerate(feature_keys, start=1):
                grads[i] += diff * z[key]
        for i in range(len(beta)):
            beta[i] -= lr * grads[i] / n
    return beta


def expected_jump(jump_sizes: Iterable[float]) -> float:
    """Return mean absolute jump size."""
    sizes = [abs(js) for js in jump_sizes]
    return sum(sizes) / len(sizes) if sizes else 0.0


def llrti_hazard(
    depth_changes: Iterable[float],
    price_change: float,
    delta_t: float,
    delta: float,
    beta: Sequence[float],
    feature_keys: Sequence[str] = ("LLRTI",),
    *,
    state_z: Mapping[str, float] | None = None,
    spread: float | None = None,
    taker_fee: float | None = None,
    impact: float | None = None,
    jump_sizes: Iterable[float] | None = None,
) -> dict:
    """Return LLRTI index, hazard probability, expected jump, and optional cost."""
    index = llrti(depth_changes, price_change, delta_t, delta)
    z = {"LLRTI": index}
    if state_z:
        z.update(state_z)
    hazard = hazard_probability(z, beta, feature_keys)
    ej = expected_jump(jump_sizes) if jump_sizes is not None else 0.0
    result = {
        "llrti": index,
        "hazard": hazard,
        "expected_jump": ej,
        "hazard_jump": hazard * ej,
    }
    if spread is not None and taker_fee is not None and impact is not None:
        result["cost"] = execution_cost(spread, taker_fee, impact)
    return result


__all__ = [
    "label_jumps",
    "fit_llrti_jump_model",
    "expected_jump",
    "llrti_hazard",
]
