"""Execution-Driven Velocity Hazard indicator module.

Cached keys
-----------
``ofi``
    Order-flow imbalance.
``spread_z``
    Spread z-score.
``cum_depth_a``
    Cumulative depth on the ask side.
``cum_depth_b``
    Cumulative depth on the bid side.
``edvh_up``
    Hazard score for the ask side.
``edvh_down``
    Hazard score for the bid side.
``alpha``
    Difference between ``edvh_up`` and ``edvh_down``.
"""

# Source: docs/alphadocs/ideas/gpt5pro/Execution-Driven Velocity Hazard.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "execution_velocity_hazard",
    "interval": "1d",
    "asset": "sample",
}

try:  # pragma: no cover - allow running tests without qmtl installed
    from qmtl.transforms.execution_velocity_hazard import execution_velocity_hazard
except ModuleNotFoundError:  # pragma: no cover - simplified fallback
    import math

    def execution_velocity_hazard(
        aevx_ex: float,
        tension: float,
        depth: float,
        ofi: float,
        spread_z: float,
        micro_slope: float,
        gaps,
        cum_depth,
        eta,
        q_quantile: float,
        zeta: float = 0.5,
    ) -> float:
        x = (
            eta[0]
            + eta[1] * aevx_ex
            + eta[2] * tension
            + eta[3] * (-math.log(depth + 1e-9))
            + eta[4] * ofi
            + eta[5] * spread_z
            + eta[6] * micro_slope
        )
        hazard = 1.0 / (1.0 + math.exp(-x))
        gaps = list(gaps)
        depths = list(cum_depth)
        if gaps:
            base = gaps[0]
            tail = 0.0
            for gap, depth_val in zip(gaps[1:], depths[1:]):
                pj = 1.0 if depth_val <= q_quantile else 0.5
                tail += pj * gap
            jump = base + zeta * tail
        else:
            jump = 0.0
        return hazard * jump


def execution_velocity_hazard_node(data: dict, cache: dict | None = None) -> dict:
    """Compute EDVH for both sides and derive a simple alpha.

    Parameters
    ----------
    data:
        Mapping of parameters.
    cache:
        Optional mutable dictionary for storing and retrieving intermediate
        metrics.
    """

    cache = cache if cache is not None else {}

    ofi = data.get("ofi") if "ofi" in data else cache.get("ofi")
    spread_z = data.get("spread_z") if "spread_z" in data else cache.get("spread_z")
    depth_cum_a = (
        data.get("cum_depth_a") if "cum_depth_a" in data else cache.get("cum_depth_a")
    )
    depth_cum_b = (
        data.get("cum_depth_b") if "cum_depth_b" in data else cache.get("cum_depth_b")
    )

    # If required inputs are cached and hazard already computed, reuse result.
    if (
        ofi is not None
        and spread_z is not None
        and depth_cum_a is not None
        and depth_cum_b is not None
        and all(k in cache for k in ("edvh_up", "edvh_down", "alpha"))
        and not any(k in data for k in ("ofi", "spread_z", "cum_depth_a", "cum_depth_b"))
    ):
        return {"edvh_up": cache["edvh_up"], "edvh_down": cache["edvh_down"], "alpha": cache["alpha"]}

    aevx_ex = data.get("aevx_ex", 0.0)
    t_a = data.get("tension_a", 0.0)
    t_b = data.get("tension_b", 0.0)
    depth_a = data.get("depth_a", 1.0)
    depth_b = data.get("depth_b", 1.0)
    micro = data.get("micro_slope", 0.0)
    gaps_a = data.get("gaps_a", [0.0])
    gaps_b = data.get("gaps_b", [0.0])
    eta_L = data.get("eta_L", [0.0] * 7)
    eta_S = data.get("eta_S", [0.0] * 7)
    q_quantile = data.get("Qq", 0.0)
    zeta = data.get("zeta", 0.5)

    # Fallback defaults when still missing
    ofi = ofi if ofi is not None else 0.0
    spread_z = spread_z if spread_z is not None else 0.0
    depth_cum_a = depth_cum_a if depth_cum_a is not None else [0.0]
    depth_cum_b = depth_cum_b if depth_cum_b is not None else [0.0]

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

    cache.update(
        {
            "ofi": ofi,
            "spread_z": spread_z,
            "cum_depth_a": depth_cum_a,
            "cum_depth_b": depth_cum_b,
            "edvh_up": up,
            "edvh_down": down,
            "alpha": alpha,
        }
    )

    return {"edvh_up": up, "edvh_down": down, "alpha": alpha}
