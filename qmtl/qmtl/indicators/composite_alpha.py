"""Composite alpha indicator aggregating sub-signals."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

__all__ = ["composite_alpha_node"]


def composite_alpha_node(
    data: Mapping[str, Any],
    *,
    indicators: Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]],
    default_weight: float = 1.0,
) -> dict[str, Any]:
    """Combine multiple sub-alpha indicators using optional weights.

    Parameters
    ----------
    data:
        Mapping providing sub-indicator inputs. A special key ``"weights"``
        may supply per-indicator weights.
    indicators:
        Mapping of indicator name to callable. This enables dependency
        injection so callers can choose which indicators are available.
    default_weight:
        Weight applied when an indicator has no explicit weight.

    Returns
    -------
    dict
        Dictionary containing the overall ``alpha`` and a ``components``
        mapping of individual indicator contributions.
    """

    weights: Mapping[str, float] = data.get("weights", {})  # type: ignore[assignment]
    components: dict[str, float] = {}
    total_weight = 0.0
    weighted_sum = 0.0

    for name, func in indicators.items():
        result = func(data.get(name, {}))
        alpha = float(result.get("alpha", 0.0))
        weight = float(weights.get(name, default_weight))
        components[name] = alpha
        weighted_sum += alpha * weight
        total_weight += weight

    alpha = weighted_sum / total_weight if total_weight else 0.0
    return {"alpha": alpha, "components": components}
