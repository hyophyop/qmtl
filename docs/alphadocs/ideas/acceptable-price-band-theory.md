# Acceptable Price Band Theory

An acceptable price band adapts to market conditions using exponential smoothing.

## Band estimation

```
mu = (1 - lambda_mu) * mu_prev + lambda_mu * price
resid = price - mu
sigma = sqrt((1 - lambda_sigma) * sigma_prev**2 + lambda_sigma * resid**2)
band_lower = mu - k * sigma
band_upper = mu + k * sigma
pbx = resid / (k * sigma) if sigma else 0
```

## Overshoot and volume surprise

```
overshoot = max(0, abs(resid) - k * sigma) / sigma
volume_surprise = (volume - volume_hat) / volume_std
```

These measures flag excursions beyond the band and unexpected volume bursts.
