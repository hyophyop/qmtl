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

    # Band estimation via exponential smoothing
    mu = (1 - lambda_mu) * mu_prev + lambda_mu * price
    resid = price - mu
    sigma = math.sqrt((1 - lambda_sigma) * (sigma_prev ** 2) + lambda_sigma * (resid ** 2))

    # Normalized deviation and overshoot beyond the band
    denom = k * sigma if sigma else 0.0
    pbx = resid / denom if denom else 0.0
    overshoot = max(0.0, abs(resid) - k * sigma) / sigma if sigma else 0.0

    # Volume surprise normalized by seasonal forecast
    volume_surprise = (volume - volume_hat) / volume_std if volume_std else 0.0

    sign = 1.0 if resid >= 0 else -1.0
    gate = 1.0 / (1.0 + math.exp(-(overshoot + volume_surprise)))
    alpha_mom = math.log1p(math.exp(overshoot)) * (1.0 + volume_surprise) * sign
    inner = (k * sigma - abs(resid)) / sigma if sigma else 0.0
    alpha_rev = -math.log1p(math.exp(inner)) * sign
    alpha = gate * alpha_mom + (1.0 - gate) * alpha_rev

    return {
        "mu": mu,
        "sigma": sigma,
        "band_lower": mu - k * sigma,
        "band_upper": mu + k * sigma,
        "pbx": pbx,
        "alpha": alpha,
        "volume_surprise": volume_surprise,
    }

