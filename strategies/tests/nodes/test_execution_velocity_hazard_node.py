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
    out = execution_velocity_hazard_node(data, {})
    assert "alpha" in out
    assert isinstance(out["alpha"], float)


def test_execution_velocity_hazard_cached_retrieval():
    cache: dict = {}
    base = {
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
    first = execution_velocity_hazard_node(base, cache)

    # Drop cached inputs from the second call to force cache retrieval.
    follow_up = {
        key: base[key]
        for key in (
            "aevx_ex",
            "tension_a",
            "tension_b",
            "depth_a",
            "depth_b",
            "micro_slope",
            "gaps_a",
            "gaps_b",
            "eta_L",
            "eta_S",
            "Qq",
        )
    }

    second = execution_velocity_hazard_node(follow_up, cache)
    assert first == second
    # Ensure cache now holds hazard and intermediate metrics
    assert cache["ofi"] == base["ofi"]
    assert cache["edvh_up"] == first["edvh_up"]
