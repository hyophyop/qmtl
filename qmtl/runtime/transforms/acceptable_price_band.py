"""Acceptable price band transform utilities."""

# Source: ../docs/alphadocs/ideas/gpt5pro/Acceptable Price Band Theory.md
# Priority: gpt5pro

from __future__ import annotations

import math


def estimate_band(
    price: float,
    mu_prev: float,
    sigma_prev: float,
    lambda_mu: float,
    lambda_sigma: float,
    k: float,
) -> dict:
    """Return updated band statistics.

    Parameters
    ----------
    price, mu_prev, sigma_prev, lambda_mu, lambda_sigma, k
        Inputs for exponential smoothing band estimation.

    Returns
    -------
    dict
        Mapping with ``mu``, ``sigma``, ``band_lower``, ``band_upper``,
        ``pbx`` and ``resid`` (the price minus ``mu``).
    """

    mu = (1 - lambda_mu) * mu_prev + lambda_mu * price
    resid = price - mu
    sigma = math.sqrt((1 - lambda_sigma) * (sigma_prev ** 2) + lambda_sigma * (resid ** 2))
    band_lower = mu - k * sigma
    band_upper = mu + k * sigma
    denom = k * sigma if sigma else 0.0
    pbx = resid / denom if denom else 0.0
    return {
        "mu": mu,
        "sigma": sigma,
        "band_lower": band_lower,
        "band_upper": band_upper,
        "pbx": pbx,
        "resid": resid,
    }


def overshoot(resid: float, sigma: float, k: float) -> float:
    """Return normalized overshoot beyond the acceptable band."""
    if sigma <= 0:
        return 0.0
    return max(0.0, abs(resid) - k * sigma) / sigma


def volume_surprise(volume: float, volume_hat: float, volume_std: float) -> float:
    """Return normalized volume deviation from seasonal expectation."""
    if volume_std == 0:
        return 0.0
    return (volume - volume_hat) / volume_std


def pbx_delta(pbx: float, pbx_prev: float) -> float:
    """Return change in normalized price band excursion (PBX)."""
    return pbx - pbx_prev


def ofi_liquidity_gap(bid_ofi: float, ask_ofi: float) -> float:
    """Return liquidity gap derived from order flow imbalance."""
    return bid_ofi - ask_ofi


def volatility_squeeze(sigma_short: float, sigma_long: float) -> float:
    """Return relative contraction of short- vs long-horizon volatility."""
    if sigma_long == 0:
        return 0.0
    return sigma_short / sigma_long - 1.0


def iv_hv_spread(iv: float, hv: float) -> float:
    """Return difference between implied and historical volatility."""
    return iv - hv
