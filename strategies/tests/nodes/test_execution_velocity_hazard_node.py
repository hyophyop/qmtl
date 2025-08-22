from strategies.nodes.indicators.execution_velocity_hazard import (
    execution_velocity_hazard_node,
)


def test_execution_velocity_hazard_node_outputs():
    data = {
        "aevx_ex": 0.5,
        "tension_a": 0.2,
        "tension_b": 0.1,
        "depth_a": 1.0,
        "depth_b": 1.0,
        "ofi": 0.1,
        "spread_z": 0.0,
        "micro_slope": 0.0,
        "gaps_a": [0.5, 1.0],
        "gaps_b": [0.5, 1.0],
        "cum_depth_a": [0.5, 1.5],
        "cum_depth_b": [0.5, 1.5],
        "eta_L": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "eta_S": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "Qq": 1.0,
    }
    out = execution_velocity_hazard_node(data)
    assert "alpha" in out
    assert isinstance(out["alpha"], float)
