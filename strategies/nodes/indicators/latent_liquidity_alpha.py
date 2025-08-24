"""Non-linear alpha from GPT-5-Pro: log LLRTI^γ plus exec imbalance derivative."""
# Source: docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "latent_liquidity_alpha",
    "interval": "1d",
    "asset": "sample",
}

import math
from .latent_liquidity_cache import CACHE_NS, _cache_category  # noqa: F401


def latent_liquidity_alpha_node(data: dict, cache: dict | None = None) -> dict:
    """Compute cost-aware alpha scaled by hazard times expected jump."""

    cache = cache if cache is not None else {}
    time = data.get("time", 0)
    side = data.get("side", "buy")
    level = data.get("level", 0)

    llrti_cat = _cache_category(cache, "llrti")
    llrti_val = data.get("llrti", llrti_cat.get((time, side, level), 0.0))

    hazard_jump_cat = _cache_category(cache, "llrti_hazard_jump")
    hazard_jump = data.get(
        "hazard_jump", hazard_jump_cat.get((time, side, level), 0.0)
    )
    hazard_jump_cat[(time, side, level)] = hazard_jump

    cost_cat = _cache_category(cache, "llrti_cost")
    cost = data.get("cost", cost_cat.get((time, side, level), 0.0))
    cost_cat[(time, side, level)] = cost

    gamma = data.get("gamma", 1.0)
    theta1 = data.get("theta1", 1.0)
    theta2 = data.get("theta2", 1.0)

    exec_delta_cat = _cache_category(cache, "exec_delta")
    exec_deriv = data.get(
        "exec_imbalance_deriv", exec_delta_cat.get((time, side, level), 0.0)
    )
    exec_delta_cat[(time, side, level)] = exec_deriv

    base_alpha = theta1 * math.log(1 + abs(llrti_val) ** gamma) + theta2 * abs(
        exec_deriv
    )
    direction = 1.0 if exec_deriv > 0 else -1.0 if exec_deriv < 0 else 0.0
    scaled_alpha = direction * hazard_jump * base_alpha / (1.0 + cost)
    return {"alpha": scaled_alpha}
