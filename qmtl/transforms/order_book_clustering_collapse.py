"""Order book clustering collapse transforms."""

# Source: ../docs/alphadocs/ideas/order-book-clustering-collapse-theory.md

from __future__ import annotations

from .hazard_utils import hazard_probability as _hazard_probability
from .hazard_utils import direction_signal as _direction_signal
from .hazard_utils import execution_cost


def hazard_probability(z: dict[str, float], beta: tuple[float, ...]) -> float:
    """Return hazard probability from z-scores using :mod:`hazard_utils`."""
    feature_keys = ["C", "Cliff", "Gap", "CH", "RL", "Shield", "QDT_inv"]
    return _hazard_probability(
        z,
        beta,
        feature_keys,
        softplus_keys=("C",),
        negative_keys=("Shield",),
    )


def direction_gating(side: int, z: dict[str, float], eta: tuple[float, ...]) -> float:
    """Return side-aware direction gating using :mod:`hazard_utils`."""
    return _direction_signal(side, z, eta)


__all__ = ["hazard_probability", "direction_gating", "execution_cost"]
