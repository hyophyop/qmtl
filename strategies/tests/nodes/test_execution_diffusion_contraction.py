import pytest

from strategies.nodes.indicators.execution_diffusion_contraction import (
    execution_diffusion_contraction_node,
)


def test_execution_diffusion_contraction_node():
    data = {
        "up_prob": 0.6,
        "up_jump": 1.0,
        "down_prob": 0.4,
        "down_jump": 0.5,
    }
    out = execution_diffusion_contraction_node(data)
    assert out["edch_up"] == pytest.approx(0.6)
    assert out["edch_down"] == pytest.approx(0.2)
    assert out["alpha"] == pytest.approx(0.6 - 0.2)
