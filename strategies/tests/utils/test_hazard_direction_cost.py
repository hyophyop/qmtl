import pytest

from strategies.utils.hazard_direction_cost import (
    hazard_probability,
    direction_signal,
    execution_cost,
)
from qmtl.transforms.order_book_clustering_collapse import (
    hazard_probability as occ_hazard_probability,
    direction_gating as occ_direction_gating,
    execution_cost as occ_execution_cost,
)
from qmtl.transforms.tactical_liquidity_bifurcation import (
    bifurcation_hazard,
    direction_signal as tlb_direction_signal,
)


def test_hazard_probability_matches_occ():
    z = {"C": 0.5, "Cliff": -0.1, "Gap": 0.2, "CH": 0.3, "RL": -0.4, "Shield": 0.1, "QDT_inv": 0.0}
    beta = (0.1, 0.2, -0.3, 0.4, 0.5, -0.6, 0.7, -0.8)
    feature_keys = ["C", "Cliff", "Gap", "CH", "RL", "Shield", "QDT_inv"]
    expected = occ_hazard_probability(z, beta)
    result = hazard_probability(
        z,
        beta,
        feature_keys,
        softplus_keys=("C",),
        negative_keys=("Shield",),
    )
    assert result == pytest.approx(expected)


def test_hazard_probability_matches_tlb():
    z = {
        "SkewDot": 0.1,
        "CancelDot": -0.2,
        "Gap": 0.3,
        "Cliff": -0.4,
        "Shield": 0.5,
        "QDT_inv": 0.0,
        "RequoteLag": 0.2,
    }
    beta = (0.0, 0.1, 0.2, -0.3, 0.4, -0.5, 0.6, 0.7)
    feature_keys = ["SkewDot", "CancelDot", "Gap", "Cliff", "Shield", "QDT_inv", "RequoteLag"]
    expected = bifurcation_hazard(z, beta)
    result = hazard_probability(
        z,
        beta,
        feature_keys,
        softplus_keys=("SkewDot", "CancelDot"),
        negative_keys=("Shield",),
    )
    assert result == pytest.approx(expected)


def test_direction_signal_matches_occ():
    z = {"OFI": 0.5, "MicroSlope": -0.2, "AggFlow": 0.1}
    eta = (0.1, 0.2, -0.3, 0.4)
    expected = occ_direction_gating(+1, z, eta)
    result = direction_signal(+1, z, eta)
    assert result == pytest.approx(expected)


def test_direction_signal_matches_tlb():
    z = {"OFI": -0.5, "MicroSlope": 0.2, "AggFlow": -0.1}
    eta = (0.1, 0.2, -0.3, 0.4)
    expected = tlb_direction_signal(-1, z, eta)
    result = direction_signal(-1, z, eta, weight_aggflow_by_ofi=True)
    assert result == pytest.approx(expected)


def test_execution_cost_matches_transform():
    assert execution_cost(0.2, 0.01, 0.05) == pytest.approx(
        occ_execution_cost(0.2, 0.01, 0.05)
    )
