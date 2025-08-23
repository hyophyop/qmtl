"""Execution-Driven Velocity Hazard indicator module.

Cache Key Scheme
----------------
Metrics are stored in a :class:`~strategies.utils.four_dim_cache.FourDimCache`
using ``(timestamp, side, level, metric)`` keys. ``side`` is ``"ask"`` or
``"bid"`` for depth and hazard values and ``"both"`` for shared quantities
such as ``ofi`` or ``alpha``.
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


from strategies.utils.four_dim_cache import FourDimCache


CACHE = FourDimCache()


def execution_velocity_hazard_node(
    data: dict, cache: FourDimCache | None = None
) -> dict:
    """Compute EDVH for both sides and derive a simple alpha.

    Parameters
    ----------
    data:
        Mapping of parameters.
    cache:
        Optional cache instance. Defaults to a module level cache.
    """

    cache = cache or CACHE
    ts = data.get("timestamp")

    ofi = data.get("ofi")
    if ofi is None:
        ofi = cache.get(ts, "both", 0, "ofi")
    else:
        cache.set(ts, "both", 0, "ofi", ofi)

    spread_z = data.get("spread_z")
    if spread_z is None:
        spread_z = cache.get(ts, "both", 0, "spread_z")
    else:
        cache.set(ts, "both", 0, "spread_z", spread_z)

    depth_cum_a = data.get("cum_depth_a")
    if depth_cum_a is None:
        depth_cum_a = cache.get(ts, "ask", 0, "cum_depth")
    else:
        cache.set(ts, "ask", 0, "cum_depth", depth_cum_a)

    depth_cum_b = data.get("cum_depth_b")
    if depth_cum_b is None:
        depth_cum_b = cache.get(ts, "bid", 0, "cum_depth")
    else:
        cache.set(ts, "bid", 0, "cum_depth", depth_cum_b)

    cached_up = cache.get(ts, "ask", 0, "edvh_up")
    cached_down = cache.get(ts, "bid", 0, "edvh_down")
    cached_alpha = cache.get(ts, "both", 0, "alpha")
    if (
        cached_up is not None
        and cached_down is not None
        and cached_alpha is not None
        and not any(k in data for k in ("ofi", "spread_z", "cum_depth_a", "cum_depth_b"))
    ):
        return {"edvh_up": cached_up, "edvh_down": cached_down, "alpha": cached_alpha}

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

    cache.set(ts, "both", 0, "ofi", ofi)
    cache.set(ts, "both", 0, "spread_z", spread_z)
    cache.set(ts, "ask", 0, "cum_depth", depth_cum_a)
    cache.set(ts, "bid", 0, "cum_depth", depth_cum_b)
    cache.set(ts, "ask", 0, "edvh_up", up)
    cache.set(ts, "bid", 0, "edvh_down", down)
    cache.set(ts, "both", 0, "alpha", alpha)

    return {"edvh_up": up, "edvh_down": down, "alpha": alpha}
