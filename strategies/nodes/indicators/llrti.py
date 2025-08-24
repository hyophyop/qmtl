"""Compute LLRTI baseline from GPT-5-Pro: sum depth change rate when |ΔP| > δ."""
# Source: docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "llrti",
    "interval": "1d",
    "asset": "sample",
}

try:  # pragma: no cover - fallback when qmtl is unavailable
    from qmtl.transforms import llrti_hazard
except ModuleNotFoundError:  # pragma: no cover - simple local implementation
    import math

    def llrti_hazard(
        depth_changes,
        price_change,
        delta_t,
        delta,
        beta,
        *,
        spread=None,
        taker_fee=None,
        impact=None,
    ):  # type: ignore[override]
        if delta_t <= 0 or abs(price_change) <= delta:
            index = 0.0
        else:
            index = sum(depth_changes) / delta_t
        b0, b1 = beta
        hazard = 1.0 / (1.0 + math.exp(-(b0 + b1 * index)))
        result = {"llrti": index, "hazard": hazard}
        if spread is not None and taker_fee is not None and impact is not None:
            result["cost"] = spread / 2 + taker_fee + impact
        return result

from .latent_liquidity_cache import CACHE_NS, _cache_category  # noqa: F401


def llrti_node(data: dict, cache: dict | None = None) -> dict:
    """Calculate LLRTI hazard metrics and store them in a shared cache."""

    cache = cache if cache is not None else {}
    time = data.get("time", 0)
    side = data.get("side", "buy")
    level = data.get("level", 0)

    depth_changes = data.get("depth_changes")
    if depth_changes is not None:
        seq = list(depth_changes)
        depth_change = seq[-1] if seq else 0.0
    else:
        depth_change = data.get("depth_change", 0.0)
        depth_cat = _cache_category(cache, "depth_changes")
        seq = [
            val
            for (t, s, l), val in sorted(depth_cat.items())
            if s == side and l == level and t < time
        ]
        seq.append(depth_change)
        depth_cat[(time, side, level)] = depth_change

    result = llrti_hazard(
        seq,
        data.get("price_change", 0.0),
        data.get("delta_t", 1.0),
        data.get("delta", 0.0),
        data.get("beta", (0.0, 1.0)),
        data.get("feature_keys", ("LLRTI",)),
        state_z=data.get("state_z"),
        spread=data.get("spread"),
        taker_fee=data.get("taker_fee"),
        impact=data.get("impact"),
        jump_sizes=data.get("jump_sizes"),
    )

    llrti_cat = _cache_category(cache, "llrti")
    llrti_cat[(time, side, level)] = result["llrti"]
    hazard_cat = _cache_category(cache, "llrti_hazard")
    hazard_cat[(time, side, level)] = result["hazard"]
    hazard_jump_cat = _cache_category(cache, "llrti_hazard_jump")
    hazard_jump_cat[(time, side, level)] = result["hazard_jump"]
    if "cost" in result:
        cost_cat = _cache_category(cache, "llrti_cost")
        cost_cat[(time, side, level)] = result["cost"]
    return result
