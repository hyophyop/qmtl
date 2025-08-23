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
    from qmtl.transforms import llrti
except ModuleNotFoundError:  # pragma: no cover - simple local implementation
    def llrti(depth_changes, price_change, delta_t, delta):  # type: ignore[override]
        if delta_t <= 0 or abs(price_change) <= delta:
            return 0.0
        return sum(depth_changes) / delta_t

from .latent_liquidity_cache import CACHE_NS, _cache_category  # noqa: F401


def llrti_node(data: dict, cache: dict | None = None) -> dict:
    """Calculate LLRTI and store depth change and index in a shared cache."""

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

    index = llrti(
        seq,
        data.get("price_change", 0.0),
        data.get("delta_t", 1.0),
        data.get("delta", 0.0),
    )

    llrti_cat = _cache_category(cache, "llrti")
    llrti_cat[(time, side, level)] = index
    return {"llrti": index}
