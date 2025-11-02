"""Contract tests for :mod:`qmtl.runtime.transforms.order_book_inertia`."""

from __future__ import annotations

import math

import pytest

from qmtl.runtime.transforms.order_book_imbalance import order_book_imbalance
from qmtl.runtime.transforms.order_book_inertia import (
    obii_from_survival,
    order_book_inertia,
)


def test_obii_ignores_non_finite_hazard_scores() -> None:
    """Non-finite hazard inputs fall back to neutral contributions."""

    hazard_z = [0.2, float("inf"), float("-inf"), float("nan"), -0.1]
    baseline = [0.3] * len(hazard_z)
    weights = [0.2] * len(hazard_z)

    sanitized = [z if math.isfinite(z) else -30.0 for z in hazard_z]

    raw = obii_from_survival(hazard_z, baseline, weights, 0.0, 0.0, 0.0)
    expected = obii_from_survival(sanitized, baseline, weights, 0.0, 0.0, 0.0)

    assert raw == pytest.approx(expected)


def test_obii_ignores_unit_baseline_levels() -> None:
    """Levels with baseline hazard of one are skipped to avoid singularities."""

    hazard_z = [0.4, -0.3, 0.1]
    baseline = [0.2, 1.0, 0.25]
    weights = [0.3, 0.3, 0.4]
    spread, depth, ofi = 0.4, 1.25, -0.2

    trimmed = obii_from_survival(
        [hazard_z[0], hazard_z[2]],
        [baseline[0], baseline[2]],
        [weights[0], weights[2]],
        spread,
        depth,
        ofi,
    )
    result = obii_from_survival(hazard_z, baseline, weights, spread, depth, ofi)

    assert result == pytest.approx(trimmed)


def test_obii_scales_linearly_with_weight_multiplier() -> None:
    """Scaling all weights by a constant scales the OBII by the same constant."""

    hazard_z = [0.25, -0.5]
    baseline = [0.1, 0.35]
    weights = [0.6, 0.4]
    spread, depth, ofi = 0.5, 2.0, -1.0

    base = obii_from_survival(hazard_z, baseline, weights, spread, depth, ofi)
    doubled = obii_from_survival(
        hazard_z,
        baseline,
        [w * 2 for w in weights],
        spread,
        depth,
        ofi,
    )

    assert doubled == pytest.approx(base * 2)


def test_obii_normalization_damps_large_market_state() -> None:
    """Large spread/depth/OFI magnitudes dampen the normalized output."""

    hazard_z = [0.0, 0.15]
    baseline = [0.2, 0.25]
    weights = [0.5, 0.5]

    calm = obii_from_survival(hazard_z, baseline, weights, 0.05, 0.5, 0.1)
    stressed = obii_from_survival(hazard_z, baseline, weights, 4.0, 10.0, -6.0)

    assert math.copysign(1.0, calm) == math.copysign(1.0, stressed)
    assert abs(stressed) < abs(calm)


def test_order_book_inertia_returns_obii_and_queue_imbalance() -> None:
    """Combined helper exposes OBII value and queue imbalance from order books."""

    hazard_z = [0.3, -0.7]
    baseline = [0.2, 0.15]
    weights = [0.4, 0.6]
    spread, depth, ofi = 0.25, 1.5, -0.3
    bid_volume, ask_volume = 1200.0, 800.0

    obii_value, qi_value = order_book_inertia(
        hazard_z,
        baseline,
        weights,
        spread,
        depth,
        ofi,
        bid_volume,
        ask_volume,
    )

    assert obii_value == pytest.approx(
        obii_from_survival(hazard_z, baseline, weights, spread, depth, ofi)
    )
    assert qi_value == pytest.approx(order_book_imbalance(bid_volume, ask_volume))
