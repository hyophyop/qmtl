"""Compute LLRTI baseline from GPT-5-Pro: sum depth change rate when |ΔP| > δ."""
# Source: docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "llrti",
    "interval": "1d",
    "asset": "sample",
}

from collections.abc import Mapping
from qmtl.transforms import llrti

CACHE_NS = "latent_liquidity"


def _cache_category(cache: Mapping, name: str) -> dict:
    ns = cache.setdefault(CACHE_NS, {})  # type: ignore[arg-type]
    return ns.setdefault(name, {})  # type: ignore[return-value]


def llrti_node(data: dict, cache: dict | None = None) -> dict:
    """Calculate LLRTI and store depth change and index in a shared cache."""

    cache = cache if cache is not None else {}
    time = data.get("time", 0)
    side = data.get("side", "buy")
    level = data.get("level", 0)
    depth_change = data.get("depth_change", 0.0)

    depth_cat = _cache_category(cache, "depth_changes")
    seq = [
        val
        for (t, s, l), val in sorted(depth_cat.items())
        if s == side and l == level and t < time
    ]
    seq.append(depth_change)

    index = llrti(
        seq,
        data.get("price_change", 0.0),
        data.get("delta_t", 1.0),
        data.get("delta", 0.0),
    )

    depth_cat[(time, side, level)] = depth_change
    llrti_cat = _cache_category(cache, "llrti")
    llrti_cat[(time, side, level)] = index
    return {"llrti": index}
