# Resiliency

Resiliency quantifies how quickly markets absorb trades and revert to equilibrium.

## Impact

A simplified impact model scales trade volume by typical size and book depth:

```
impact = beta * (volume / avg_volume) / depth
```

## Alpha

The resiliency alpha rewards markets that recover after impact and penalizes volatility and order book imbalance derivatives:

```
alpha = gamma * impact - volatility + obi_derivative
```
