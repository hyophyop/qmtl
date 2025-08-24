"""LLRTI hazard transform combining index and jump probability."""
# Source: docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md
# Priority: gpt5pro

from __future__ import annotations

from math import exp
from typing import Iterable, Sequence

from .llrti import llrti
from .hazard_utils import hazard_probability, execution_cost


def fit_llrti_jump_model(
    llrti_values: Iterable[float],
    jump_labels: Iterable[int],
    lr: float = 0.1,
    epochs: int = 100,
) -> Sequence[float]:
    """Estimate logistic regression coefficients for jump probability.

    Parameters
    ----------
    llrti_values:
        Sequence of observed LLRTI values.
    jump_labels:
        Corresponding binary labels indicating whether a jump occurred.
    lr:
        Gradient descent learning rate.
    epochs:
        Number of training iterations.
    """
    x = list(llrti_values)
    y = list(jump_labels)
    if len(x) != len(y):
        raise ValueError("Mismatched feature and label lengths")
    b0 = 0.0
    b1 = 0.0
    n = len(x)
    for _ in range(epochs):
        g0 = 0.0
        g1 = 0.0
        for xi, yi in zip(x, y):
            p = 1.0 / (1.0 + exp(-(b0 + b1 * xi)))
            diff = p - yi
            g0 += diff
            g1 += diff * xi
        b0 -= lr * g0 / n
        b1 -= lr * g1 / n
    return b0, b1


def llrti_hazard(
    depth_changes: Iterable[float],
    price_change: float,
    delta_t: float,
    delta: float,
    beta: Sequence[float],
    *,
    spread: float | None = None,
    taker_fee: float | None = None,
    impact: float | None = None,
) -> dict:
    """Return LLRTI index, hazard probability, and optional cost."""
    index = llrti(depth_changes, price_change, delta_t, delta)
    hazard = hazard_probability({"LLRTI": index}, beta, ["LLRTI"])
    result = {"llrti": index, "hazard": hazard}
    if spread is not None and taker_fee is not None and impact is not None:
        result["cost"] = execution_cost(spread, taker_fee, impact)
    return result


__all__ = ["fit_llrti_jump_model", "llrti_hazard"]
