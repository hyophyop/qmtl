"""Execution-Driven Velocity Hazard indicator module."""

# Source: docs/alphadocs/ideas/gpt5pro/Execution-Driven Velocity Hazard.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "execution_velocity_hazard",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms.execution_velocity_hazard import execution_velocity_hazard


def execution_velocity_hazard_node(data: dict) -> dict:
    """Compute EDVH for both sides and derive a simple alpha."""
    aevx_ex = data.get("aevx_ex", 0.0)
    t_a = data.get("tension_a", 0.0)
    t_b = data.get("tension_b", 0.0)
    depth_a = data.get("depth_a", 1.0)
    depth_b = data.get("depth_b", 1.0)
    ofi = data.get("ofi", 0.0)
    spread_z = data.get("spread_z", 0.0)
    micro = data.get("micro_slope", 0.0)
    gaps_a = data.get("gaps_a", [0.0])
    gaps_b = data.get("gaps_b", [0.0])
    depth_cum_a = data.get("cum_depth_a", [0.0])
    depth_cum_b = data.get("cum_depth_b", [0.0])
    eta_L = data.get("eta_L", [0.0] * 7)
    eta_S = data.get("eta_S", [0.0] * 7)
    q_quantile = data.get("Qq", 0.0)
    zeta = data.get("zeta", 0.5)

    up = execution_velocity_hazard(
        aevx_ex,
        t_a,
        depth_a,
        ofi,
        spread_z,
        micro,
        gaps_a,
        depth_cum_a,
        eta_L,
        q_quantile,
        zeta,
    )
    down = execution_velocity_hazard(
        -aevx_ex,
        t_b,
        depth_b,
        -ofi,
        spread_z,
        -micro,
        gaps_b,
        depth_cum_b,
        eta_S,
        q_quantile,
        zeta,
    )
    alpha = up - down
    return {"edvh_up": up, "edvh_down": down, "alpha": alpha}
