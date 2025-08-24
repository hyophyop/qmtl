from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT / "qmtl"))

from qmtl.common import FourDimCache
from strategies.nodes.indicators.order_book_inertia import order_book_inertia_node


def test_order_book_inertia_basic():
    data = {
        "timestamp": 1,
        "hazard_z": [0.0, 0.0],
        "spread": 1.0,
        "depth": 5.0,
        "ofi": 1.0,
        "bid_volume": 70.0,
        "ask_volume": 30.0,
    }
    baseline = [0.6, 0.6]
    weights = [0.5, 0.5]
    result = order_book_inertia_node(data, baseline_hazard=baseline, weights=weights)
    expected_obii = 0.03125
    expected_qi = 0.4
    expected_alpha = expected_obii * expected_qi
    assert result["obii"] == pytest.approx(expected_obii)
    assert result["qi"] == pytest.approx(expected_qi)
    assert result["alpha"] == pytest.approx(expected_alpha)


def test_order_book_inertia_uses_cache():
    cache = FourDimCache()
    baseline = [0.6, 0.6]
    weights = [0.5, 0.5]
    first = order_book_inertia_node(
        {
            "timestamp": 1,
            "hazard_z": [0.0, 0.0],
            "spread": 1.0,
            "depth": 5.0,
            "ofi": 1.0,
            "bid_volume": 70.0,
            "ask_volume": 30.0,
        },
        baseline_hazard=baseline,
        weights=weights,
        cache=cache,
    )
    second = order_book_inertia_node({"timestamp": 1}, baseline_hazard=baseline, weights=weights, cache=cache)
    assert second["obii"] == pytest.approx(first["obii"])
    assert second["qi"] == pytest.approx(first["qi"])
    assert second["alpha"] == pytest.approx(first["alpha"])
