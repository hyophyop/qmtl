"""Acceptable Price Band indicator with nonlinear alpha response."""

# Source: docs/alphadocs/ideas/gpt5pro/Acceptable Price Band Theory.md
# Priority: gpt5pro

TAGS = {
    "scope": "indicator",
    "family": "acceptable_price_band",
    "interval": "1d",
    "asset": "sample",
}

import math

from qmtl.transforms.acceptable_price_band import (
    estimate_band,
    overshoot,
    volume_surprise,
)


def acceptable_price_band_node(data: dict) -> dict:
    """Estimate price bands and nonlinear alpha.

    Parameters
    ----------
    data:
        Mapping with entries ``price`` and ``volume``. Optional keys include
        ``mu_prev`` and ``sigma_prev`` for previous estimates, ``volume_hat``
        and ``volume_std`` for seasonal volume expectation and deviation, and
        smoothing factors ``lambda_mu`` and ``lambda_sigma``. ``k`` controls
        the band width.

    Returns
    -------
    dict
        Mapping containing updated band estimates and ``alpha``.
    """

    price = data.get("price", 0.0)
    volume = data.get("volume", 0.0)
    volume_hat = data.get("volume_hat", 0.0)
    volume_std = data.get("volume_std", 1.0)
    mu_prev = data.get("mu_prev", price)
    sigma_prev = data.get("sigma_prev", 1.0)
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
    return {
        **band,
        "alpha": alpha,
        "volume_surprise": vs,
    }

