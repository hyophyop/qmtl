# Latent Liquidity Threshold Reconfiguration

The Latent Liquidity Threshold Reconfiguration Index (LLRTI) measures how quickly book depth collapses once price moves beyond a tolerance.

Given depth changes over an interval and the absolute price change $\Delta p$, the index is

```
LLRTI = sum(depth_changes) / delta_t
```

when $|\Delta p|>\delta$ and the interval duration ``delta_t`` is positive. Otherwise the index is ``0``. The measure captures latent liquidity that vanishes once prices breach a reconfiguration threshold.
