"""LLRTI transform computing liquidity loss rate triggered by price movement."""
# Source: ../docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md
# Priority: gpt5pro

from __future__ import annotations

from typing import Iterable


def llrti(
    depth_changes: Iterable[float],
    price_change: float,
    delta_t: float,
    delta: float,
) -> float:
    """Return LLRTI index.

    The LLRTI (Latency Liquidity Reconfiguration Threshold Index) aggregates
    order book depth changes only when the absolute price change exceeds the
    threshold ``delta``. The sum of depth changes is normalised by ``delta_t``.

    Parameters
    ----------
    depth_changes:
        Sequence of depth change values over the interval.
    price_change:
        Absolute price change over the same interval.
    delta_t:
        Duration of the interval. Non-positive values yield zero.
    delta:
        Price movement threshold. If ``|price_change|`` is below or equal to
        this value, the LLRTI is zero.

    Returns
    -------
    float
        The normalised sum of depth changes when the threshold is exceeded,
        otherwise ``0.0``.
    """

    if delta_t <= 0:
        return 0.0
    if abs(price_change) <= delta:
        return 0.0
    return sum(depth_changes) / delta_t
