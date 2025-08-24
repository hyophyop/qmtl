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
        "stale_quotes": 5.0,
        "total_quotes": 20.0,
        "requote_speed": 2.0,
        "qi": 0.1,
    }
    result = order_book_inertia_node(data)
    expected_obii = (5.0 / 20.0) * (1.0 / (2.0 + 1e-9))
    expected_alpha = expected_obii * 0.1
    assert result["obii"] == pytest.approx(expected_obii)
    assert result["alpha"] == pytest.approx(expected_alpha)


def test_order_book_inertia_uses_cache():
    cache = FourDimCache()
    first = order_book_inertia_node(
        {
            "timestamp": 1,
            "stale_quotes": 10.0,
            "total_quotes": 40.0,
            "requote_speed": 4.0,
            "qi": 0.2,
        },
        cache,
    )
    second = order_book_inertia_node({"timestamp": 1}, cache)
    assert second["obii"] == pytest.approx(first["obii"])
    assert second["alpha"] == pytest.approx(first["alpha"])
