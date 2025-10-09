"""Unit tests for :mod:`qmtl.runtime.transforms.order_book_inertia`."""

from __future__ import annotations

import math

import pytest

from qmtl.runtime.transforms.hazard_utils import hazard_probability
from qmtl.runtime.transforms.order_book_imbalance import order_book_imbalance
from qmtl.runtime.transforms.order_book_inertia import (
    obii_from_survival,
    order_book_inertia,
)


def _expected_obii(
    hazard_z: list[float],
    baseline_hazard: list[float],
    weights: list[float],
    *,
    spread: float = 0.0,
    depth: float = 0.0,
    ofi: float = 0.0,
) -> float:
    """Helper that mirrors the production implementation for assertions."""

    hazards = [
        hazard_probability({"z": z}, (0.0, 1.0), ("z",)) if math.isfinite(z) else 0.0
        for z in hazard_z
    ]
    terms = []
    for hazard, baseline, weight in zip(hazards, baseline_hazard, weights):
        if baseline >= 1.0:
            continue
        survival_ratio = (1.0 - hazard) / (1.0 - baseline) - 1.0
        terms.append(weight * survival_ratio)
    raw = sum(terms)
    norm = 1.0 / (1.0 + abs(spread) + depth + abs(ofi))
    return raw * norm


def test_obii_non_finite_hazard_scores_are_treated_as_zero() -> None:
    """Only finite z-scores should influence the hazard probability inputs."""

    hazard_z = [0.0, float("inf"), float("-inf"), float("nan"), 1.0]
    baseline = [0.1] * len(hazard_z)
    weights = [1.0 / len(hazard_z)] * len(hazard_z)

    result = obii_from_survival(hazard_z, baseline, weights, 0.0, 0.0, 0.0)
    expected = _expected_obii(hazard_z, baseline, weights)

    assert math.isclose(result, expected, rel_tol=1e-12, abs_tol=1e-12)


def test_obii_skips_unit_baseline_hazard_levels() -> None:
    """Levels with ``baseline_hazard`` of one must be ignored to avoid divide-by-zero."""

    hazard_z = [0.2, -0.1]
    baseline = [0.1, 1.0]
    weights = [0.5, 0.5]

    result = obii_from_survival(hazard_z, baseline, weights, 0.0, 0.0, 0.0)
    expected = _expected_obii(hazard_z, baseline, weights)

    assert result == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_obii_linear_scaling_with_weight_sum() -> None:
    """OBII responds linearly to weight scaling when all else is equal."""

    hazard_z = [0.25, -0.5]
    baseline = [0.1, 0.3]
    weights = [0.6, 0.4]  # sums to one

    base = obii_from_survival(hazard_z, baseline, weights, 0.5, 2.0, -1.0)
    expected_base = _expected_obii(hazard_z, baseline, weights, spread=0.5, depth=2.0, ofi=-1.0)

    scaled = obii_from_survival(hazard_z, baseline, [w * 2 for w in weights], 0.5, 2.0, -1.0)

    assert base == pytest.approx(expected_base, rel=1e-12, abs=1e-12)
    assert scaled == pytest.approx(base * 2, rel=1e-12, abs=1e-12)


def test_obii_normalization_damps_with_market_state_magnitude() -> None:
    """Increasing spread/depth/OFI magnitudes should dampen the normalized output."""

    hazard_z = [0.0]
    baseline = [0.2]
    weights = [1.0]

    mild = obii_from_survival(hazard_z, baseline, weights, 0.01, 0.5, 0.1)
    extreme = obii_from_survival(hazard_z, baseline, weights, 5.0, 20.0, 8.0)

    assert math.copysign(1, mild) == math.copysign(1, extreme)
    assert abs(extreme) < abs(mild)


def test_order_book_inertia_returns_obii_and_queue_imbalance() -> None:
    """The combined helper should return OBII along with the queue imbalance."""

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

    expected_obii = obii_from_survival(hazard_z, baseline, weights, spread, depth, ofi)
    expected_qi = order_book_imbalance(bid_volume, ask_volume)

    assert obii_value == pytest.approx(expected_obii, rel=1e-12, abs=1e-12)
    assert qi_value == pytest.approx(expected_qi, rel=1e-12, abs=1e-12)

