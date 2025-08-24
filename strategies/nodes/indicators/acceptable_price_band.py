"""Acceptable Price Band indicator with nonlinear alpha response.

Cache Key Scheme
----------------
Historical features are stored in a
``FourDimCache`` keyed by ``(time, side, level, metric)`` with a constant
``side`` of ``"mid"`` and ``level`` representing the ``price_level``.
"""

# Source: docs/alphadocs/ideas/gpt5pro/Acceptable Price Band Theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "acceptable_price_band",
    "interval": "1d",
    "asset": "sample",
}

import math
from collections import deque

from qmtl.transforms.acceptable_price_band import (
    estimate_band,
    overshoot,
    volume_surprise,
    pbx_delta,
    ofi_liquidity_gap,
    volatility_squeeze,
    iv_hv_spread,
)

from qmtl.common import FourDimCache


CACHE = FourDimCache()


def acceptable_price_band_node(
    data: dict, cache: FourDimCache | None = None
) -> dict:
    """Estimate price bands and nonlinear alpha.

    Parameters
    ----------
    data:
        Mapping with entries ``price`` and ``volume``. Optional keys include
        ``mu_prev`` and ``sigma_prev`` for previous estimates, ``volume_hat``
        and ``volume_std`` for seasonal volume expectation and deviation, and
        smoothing factors ``lambda_mu`` and ``lambda_sigma``. ``k`` controls
        the band width. ``cache_window`` defines the maximum history length. If
        ``mu_prev``/``sigma_prev``/``volume_hat``/``volume_std`` are omitted they
        are inferred from the cache using a simple average.
    cache:
        Optional cache instance. Defaults to a module level cache.

    Returns
    -------
    dict
        Mapping containing updated band estimates and ``alpha``.
    """

    cache = cache or CACHE
    price = data.get("price", 0.0)
    volume = data.get("volume", 0.0)
    time_key = data.get("time")
    price_level = data.get("price_level", price)
    cache_window = data.get("cache_window", 20)

    def _cached_avg(feature: str, default: float) -> float:
        values = cache.get(time_key, "mid", price_level, feature)
        if isinstance(values, deque) and len(values):
            return sum(values) / len(values)
        return default

    def _cached_last(feature: str, default: float) -> float:
        values = cache.get(time_key, "mid", price_level, feature)
        if isinstance(values, deque) and len(values):
            return values[-1]
        return default

    volume_hat = data.get(
        "volume_hat", _cached_avg("volume_hat", 0.0)
    )
    volume_std = data.get(
        "volume_std", _cached_avg("volume_std", 1.0)
    )
    mu_prev = data.get("mu_prev", _cached_avg("mu", price))
    sigma_prev = data.get("sigma_prev", _cached_avg("sigma", 1.0))
    pbx_prev = data.get("pbx_prev", _cached_last("pbx", 0.0))

    lambda_mu = data.get("lambda_mu", 0.1)
    lambda_sigma = data.get("lambda_sigma", 0.1)
    k = data.get("k", 1.0)

    band = estimate_band(
        price, mu_prev, sigma_prev, lambda_mu, lambda_sigma, k
    )
    resid = band["resid"]
    sigma = band["sigma"]
    o = overshoot(resid, sigma, k)
    vs = volume_surprise(volume, volume_hat, volume_std)
    dpbx = pbx_delta(band["pbx"], pbx_prev)
    ofi_gap = ofi_liquidity_gap(
        data.get("bid_ofi", 0.0), data.get("ask_ofi", 0.0)
    )
    vol_sq = volatility_squeeze(
        data.get("sigma_short", 0.0), data.get("sigma_long", 1.0)
    )
    ivhv = iv_hv_spread(data.get("iv", 0.0), data.get("hv", 0.0))

    coef_o = data.get("coef_overshoot", 1.0)
    coef_vs = data.get("coef_volume_surprise", 1.0)
    coef_dpbx = data.get("coef_dpbx", 0.0)
    coef_ofi = data.get("coef_ofi_gap", 0.0)
    coef_vsqueeze = data.get("coef_vol_squeeze", 0.0)
    coef_ivhv = data.get("coef_iv_hv", 0.0)
    intercept = data.get("coef_intercept", 0.0)

    gate_input = (
        intercept
        + coef_o * o
        + coef_vs * vs
        + coef_dpbx * dpbx
        + coef_ofi * ofi_gap
        + coef_vsqueeze * vol_sq
        + coef_ivhv * ivhv
    )
    sign = 1.0 if resid >= 0 else -1.0
    gate = 1.0 / (1.0 + math.exp(-gate_input))
    alpha_mom = math.log1p(math.exp(o)) * (1.0 + vs) * sign
    inner = (k * sigma - abs(resid)) / sigma if sigma else 0.0
    alpha_rev = -math.log1p(math.exp(inner)) * sign
    alpha = gate * alpha_mom + (1.0 - gate) * alpha_rev

    band.pop("resid")

    # update cache
    for feature, value in [
        ("mu", band["mu"]),
        ("sigma", band["sigma"]),
        ("volume_hat", volume_hat),
        ("volume_std", volume_std),
        ("pbx", band["pbx"]),
    ]:
        values = cache.get(time_key, "mid", price_level, feature)
        if not isinstance(values, deque) or values.maxlen != cache_window:
            values = deque(values, maxlen=cache_window) if isinstance(values, deque) else deque(
                maxlen=cache_window
            )
        values.append(value)
        cache.set(time_key, "mid", price_level, feature, values)

    return {
        **band,
        "alpha": alpha,
        "volume_surprise": vs,
        "pbx_delta": dpbx,
        "ofi_gap": ofi_gap,
        "volatility_squeeze": vol_sq,
        "iv_hv_spread": ivhv,
        "cache": cache,
    }

