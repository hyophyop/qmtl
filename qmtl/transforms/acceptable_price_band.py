"""Acceptable price band transform utilities."""

# Source: ../docs/alphadocs/ideas/acceptable-price-band-theory.md

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
