"""Execution diffusion–contraction hazard indicator.

Cache Key Scheme
----------------
All cached metrics share the ``(timestamp, side, level, metric)`` key scheme
implemented by :class:`~qmtl.common.FourDimCache`.

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
    concentration_scores,
    depth_wedge,
    hazard_probability,
    path_resistance,
    expected_jump,
    edch_side,
)

from qmtl.common import FourDimCache


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
    eta_key = f"{side}_eta"
    if prob is None and f"{side}_inputs" in data and eta_key in data:
        prob = hazard_probability(data[f"{side}_inputs"], data[eta_key])
    elif prob is None and eta_key in data:
        # Build features from raw inputs
        side_sign = 1.0 if side == "up" else -1.0
        bins = data.get("bins", 10)
        prices = data.get(f"{side}_exec_prices_ticks")
        sizes = data.get(f"{side}_exec_sizes")
        if prices is not None and sizes is not None:
            ent, hhi, fano = concentration_scores(prices, sizes, bins)
            conc = ent + hhi - fano - data.get(f"{side}_conc_baseline", 0.0)
        else:
            conc = 0.0

        lam_series = data.get(f"{side}_lambda")
        if lam_series and len(lam_series) >= 2:
            lam_grad = (lam_series[-1] - lam_series[0]) * side_sign
        else:
            lam_grad = 0.0

        up_depth = data.get("up_depth")
        down_depth = data.get("down_depth")
        resistance = path_resistance(data.get(f"{side}_depth"))
        wedge = depth_wedge(up_depth, down_depth) * side_sign

        bid_prev = data.get("bid_vol_prev", 0.0)
        bid_curr = data.get("bid_vol_curr", 0.0)
        ask_prev = data.get("ask_vol_prev", 0.0)
        ask_curr = data.get("ask_vol_curr", 0.0)
        ofi = ((bid_curr - bid_prev) - (ask_curr - ask_prev)) * side_sign

        spread = data.get("spread")
        if spread is not None:
            mean = data.get("spread_mean", 0.0)
            std = data.get("spread_std", 1.0) or 1.0
            spread_z = (spread - mean) / std
        else:
            spread_z = 0.0

        micro_prev = data.get("microprice_prev")
        micro_curr = data.get("microprice_curr")
        micro_slope = (
            (micro_curr - micro_prev) * side_sign
            if micro_prev is not None and micro_curr is not None
            else 0.0
        )

        inputs = [conc, lam_grad, resistance, ofi, spread_z, micro_slope, wedge]
        prob = hazard_probability(inputs, data[eta_key])

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
