# Tactical Liquidity Bifurcation Theory

Tactical liquidity bifurcation models the chance that order book conditions split into competing liquidity regimes and shapes order placement.

## Hazard probability

Given standardized features $Z=\{\text{SkewDot},\text{CancelDot},\text{Gap},\text{Cliff},\text{Shield},\text{QDT\_inv},\text{RequoteLag}\}$ and coefficients $\beta$, the hazard is
computed with a logistic transform. ``SkewDot`` and ``CancelDot`` pass through a softplus
while ``Shield`` enters with a negative sign.

## Direction signal

A side-aware direction signal weights aggregated flow by order flow imbalance using coefficients $\eta$.

## Alpha

The trading signal combines hazard, direction and execution cost:

```
alpha = max(hazard**gamma - tau, 0) * direction * pi * exp(-phi * cost)
```

where $\gamma$ controls curvature, $\tau$ is an activation threshold, ``pi`` reflects position incentive and ``cost`` is expected execution cost.
