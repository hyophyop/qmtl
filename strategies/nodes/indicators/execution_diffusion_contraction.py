"""Execution diffusion–contraction hazard indicator."""

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


_JUMP_CACHE: dict[tuple[str, int], float] = {}
_CUM_DEPTH_CACHE: dict[tuple[str, int], list[float]] = {}
_GAP_CACHE: dict[tuple[str, int], list[float]] = {}


def invalidate_edch_cache(
    side: str | None = None,
    level: int | None = None,
    *,
    jumps: bool = True,
    cum_depth: bool = True,
    gaps: bool = True,
) -> None:
    """Invalidate caches for specified ``side`` and ``level``.

    When ``side`` or ``level`` are ``None`` the respective dimension is
    treated as a wildcard.
    """

    def _match(key: tuple[str, int]) -> bool:
        s, lvl = key
        if side is not None and s != side:
            return False
        if level is not None and lvl != level:
            return False
        return True

    if jumps:
        for key in list(_JUMP_CACHE):
            if _match(key):
                del _JUMP_CACHE[key]
    if cum_depth:
        for key in list(_CUM_DEPTH_CACHE):
            if _match(key):
                del _CUM_DEPTH_CACHE[key]
    if gaps:
        for key in list(_GAP_CACHE):
            if _match(key):
                del _GAP_CACHE[key]


def _edch(data: dict, side: str) -> float:
    level = data.get(f"{side}_level", data.get("level", 0))
    key = (side, level)

    prob_key = f"{side}_prob"
    jump_key = f"{side}_jump"
    prob = data.get(prob_key)
    jump = data.get(jump_key)

    if prob is None and f"{side}_inputs" in data and f"{side}_eta" in data:
        prob = hazard_probability(data[f"{side}_inputs"], data[f"{side}_eta"])

    if jump is None:
        jump = _JUMP_CACHE.get(key)

    if jump is None:
        gaps = _GAP_CACHE.get(key)
        if gaps is None:
            gaps = data.get(f"{side}_gaps")
            if gaps is not None:
                _GAP_CACHE[key] = list(gaps)

        cum_depth = _CUM_DEPTH_CACHE.get(key)
        if cum_depth is None:
            cum_depth = data.get(f"{side}_cum_depth")
            if cum_depth is not None:
                _CUM_DEPTH_CACHE[key] = list(cum_depth)

        q = data.get(f"{side}_Q")
        if gaps is not None and cum_depth is not None and q is not None:
            jump = expected_jump(gaps, cum_depth, q)
            _JUMP_CACHE[key] = jump

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
