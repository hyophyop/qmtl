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

    volume_hat = data.get(
        "volume_hat", _cached_avg("volume_hat", 0.0)
    )
    volume_std = data.get(
        "volume_std", _cached_avg("volume_std", 1.0)
    )
    mu_prev = data.get("mu_prev", _cached_avg("mu", price))
    sigma_prev = data.get("sigma_prev", _cached_avg("sigma", 1.0))

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

    sign = 1.0 if resid >= 0 else -1.0
    gate = 1.0 / (1.0 + math.exp(-(o + vs)))
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
        "cache": cache,
    }

