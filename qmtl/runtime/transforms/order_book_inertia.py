"""Order Book Inertia helper transforms.

This module provides utilities to compute the Order Book Inertia Index
(OBII) using per-level quote survival estimates and to derive the
associated queue imbalance.

# Source: docs/alphadocs/ideas/gpt5pro/Order Book Inertia Theory.md
# Priority: gpt5pro
"""

from __future__ import annotations

from typing import Sequence, Tuple

from .hazard_utils import hazard_probability
from .order_book_imbalance import order_book_imbalance


def obii_from_survival(
    hazard_z: Sequence[float],
    baseline_hazard: Sequence[float],
    weights: Sequence[float],
    spread: float,
    depth: float,
    ofi: float,
) -> float:
    """Return normalized Order Book Inertia Index.

    Parameters
    ----------
    hazard_z:
        Sequence of z-scores representing per-level quote hazard.
    baseline_hazard:
        Sequence of baseline hazard probabilities for each level.
    weights:
        Per-level weights ``w`` such that ``sum(w) = 1`` is suggested.
    spread, depth, ofi:
        Market state variables used for normalization to reduce
        endogeneity.
    """

    hazards = [
        hazard_probability({"z": z}, (0.0, 1.0), ("z",)) if abs(z) < float("inf") else 0.0
        for z in hazard_z
    ]
    terms = []
    for h, b, w in zip(hazards, baseline_hazard, weights):
        if b >= 1.0:
            continue
        surv_ratio = (1.0 - h) / (1.0 - b) - 1.0
        terms.append(w * surv_ratio)
    raw = sum(terms)
    norm = 1.0 / (1.0 + abs(spread) + depth + abs(ofi))
    return raw * norm


def order_book_inertia(
    hazard_z: Sequence[float],
    baseline_hazard: Sequence[float],
    weights: Sequence[float],
    spread: float,
    depth: float,
    ofi: float,
    bid_volume: float,
    ask_volume: float,
) -> Tuple[float, float]:
    """Return ``(obii, queue_imbalance)`` from hazard inputs."""

    obii = obii_from_survival(hazard_z, baseline_hazard, weights, spread, depth, ofi)
    qi = order_book_imbalance(bid_volume, ask_volume)
    return obii, qi


__all__ = ["obii_from_survival", "order_book_inertia"]

