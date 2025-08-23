"""Execution diffusion–contraction hazard indicator.

Cache Key Scheme
----------------
All cached metrics share the ``(timestamp, side, level, metric)`` key scheme
implemented by :class:`~strategies.utils.four_dim_cache.FourDimCache`.

"""

# Source: docs/alphadocs/ideas/gpt5pro/Dynamic Execution Diffusion-Contraction Theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "execution_diffusion_contraction",
    "interval": "1d",
    "asset": "sample",
}

from qmtl.transforms.execution_diffusion_contraction import (
    hazard_probability,
    expected_jump,
    edch_side,
)

from strategies.utils.four_dim_cache import FourDimCache


CACHE = FourDimCache()


def invalidate_edch_cache(
    time: object | None = None,
    side: str | None = None,
    level: int | None = None,
    *,
    jumps: bool = True,
    cum_depth: bool = True,
    gaps: bool = True,
) -> None:
    """Invalidate cached metrics.

    Parameters default to wildcards when ``None``. ``time`` aligns the interface
    with the shared cache key scheme of :class:`FourDimCache`.
    """

    if jumps:
        CACHE.invalidate(time=time, side=side, level=level, metric="jump")
    if cum_depth:
        CACHE.invalidate(time=time, side=side, level=level, metric="cum_depth")
    if gaps:
        CACHE.invalidate(time=time, side=side, level=level, metric="gaps")


def _edch(data: dict, side: str) -> float:
    ts = data.get("timestamp")
    level = data.get(f"{side}_level", data.get("level", 0))

    prob_key = f"{side}_prob"
    prob = data.get(prob_key)
    if prob is None and f"{side}_inputs" in data and f"{side}_eta" in data:
        prob = hazard_probability(data[f"{side}_inputs"], data[f"{side}_eta"])

    jump = data.get(f"{side}_jump")
    if jump is None:
        jump = CACHE.get(ts, side, level, "jump")

    if jump is None:
        gaps = CACHE.get(ts, side, level, "gaps")
        if gaps is None:
            gaps = data.get(f"{side}_gaps")
            if gaps is not None:
                CACHE.set(ts, side, level, "gaps", list(gaps))

        cum_depth = CACHE.get(ts, side, level, "cum_depth")
        if cum_depth is None:
            cum_depth = data.get(f"{side}_cum_depth")
            if cum_depth is not None:
                CACHE.set(ts, side, level, "cum_depth", list(cum_depth))

        q = data.get(f"{side}_Q")
        if gaps is not None and cum_depth is not None and q is not None:
            jump = expected_jump(gaps, cum_depth, q)
            CACHE.set(ts, side, level, "jump", jump)

    prob = prob or 0.0
    jump = jump or 0.0
    return edch_side(prob, jump)


def execution_diffusion_contraction_node(data: dict) -> dict:
    """Compute execution diffusion–contraction hazard alpha."""

    if data.get("regime_shift"):
        invalidate_edch_cache()

    edch_up = data.get("edch_up")
    edch_down = data.get("edch_down")

    if edch_up is None:
        edch_up = _edch(data, "up")
    if edch_down is None:
        edch_down = _edch(data, "down")

    alpha = edch_up - edch_down
    return {
        "edch_up": edch_up,
        "edch_down": edch_down,
        "alpha": alpha,
    }
