"""Tactical Liquidity Bifurcation transforms."""

# Source: ../docs/alphadocs/ideas/tactical-liquidity-bifurcation-theory.md

from __future__ import annotations

from math import exp
from typing import Mapping, Sequence

from .hazard_utils import hazard_probability as _hazard_probability
from .hazard_utils import direction_signal as _direction_signal


def bifurcation_hazard(z: Mapping[str, float], beta: Sequence[float]) -> float:
    """Compute hazard probability from feature z-scores."""
    feature_keys = [
        "SkewDot",
        "CancelDot",
        "Gap",
        "Cliff",
        "Shield",
        "QDT_inv",
        "RequoteLag",
    ]
    return _hazard_probability(
        z,
        beta,
        feature_keys,
        softplus_keys=("SkewDot", "CancelDot"),
        negative_keys=("Shield",),
    )


def direction_signal(side: int, z: Mapping[str, float], eta: Sequence[float]) -> float:
    """Return side-aware direction gating signal."""
    return _direction_signal(side, z, eta, weight_aggflow_by_ofi=True)


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


__all__ = ["bifurcation_hazard", "direction_signal", "tlbh_alpha"]
