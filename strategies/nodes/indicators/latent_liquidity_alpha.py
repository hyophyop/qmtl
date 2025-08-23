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
from collections.abc import Mapping

CACHE_NS = "latent_liquidity"


def _cache_category(cache: Mapping, name: str) -> dict:
    ns = cache.setdefault(CACHE_NS, {})  # type: ignore[arg-type]
    return ns.setdefault(name, {})  # type: ignore[return-value]


def latent_liquidity_alpha_node(data: dict, cache: dict | None = None) -> dict:
    """Compute alpha from LLRTI and execution imbalance dynamics using cache."""

    cache = cache if cache is not None else {}
    time = data.get("time", 0)
    side = data.get("side", "buy")
    level = data.get("level", 0)

    llrti_cat = _cache_category(cache, "llrti")
    llrti_val = data.get("llrti", llrti_cat.get((time, side, level), 0.0))

    gamma = data.get("gamma", 1.0)
    theta1 = data.get("theta1", 1.0)
    theta2 = data.get("theta2", 1.0)

    exec_delta_cat = _cache_category(cache, "exec_delta")
    exec_deriv = data.get(
        "exec_imbalance_deriv", exec_delta_cat.get((time, side, level), 0.0)
    )
    exec_delta_cat[(time, side, level)] = exec_deriv

    alpha = theta1 * math.log(1 + abs(llrti_val) ** gamma) + theta2 * exec_deriv
    return {"alpha": alpha}
