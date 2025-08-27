import pytest

from strategies.nodes.indicators.latent_liquidity_cascade import (
    latent_liquidity_cascade_node,
)


def test_latent_liquidity_cascade_positive_gap():
    result = latent_liquidity_cascade_node(
        {
            "limit_additions": 10.0,
            "cancels": 15.0,
            "market_orders": 0.0,
            "depth": 5.0,
        }
    )
    assert result["net_flow"] == pytest.approx(-5.0)
    assert result["resiliency_gap"] == pytest.approx(5.0)
    assert result["alpha"] == pytest.approx(1.0)


def test_latent_liquidity_cascade_no_deficit():
    result = latent_liquidity_cascade_node(
        {
            "limit_additions": 20.0,
            "cancels": 5.0,
            "market_orders": 3.0,
            "depth": 10.0,
        }
    )
    assert result["net_flow"] == pytest.approx(12.0)
    assert result["resiliency_gap"] == 0.0
    assert result["alpha"] == 0.0
