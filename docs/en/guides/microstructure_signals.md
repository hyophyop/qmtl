# Microstructure Signals: Top-of-Book Imbalance and Micro-Price

Short-horizon liquidity bias is best captured with the combination of the
**top-of-book imbalance** and the **micro-price**. This page explains the new
runtime nodes shipped with QMTL and shows how to stabilise the signal using a
logistic weighting scheme.

## Top-of-Book Imbalance Node

`order_book_imbalance_node` receives the best bid/ask depth and applies

\[
I = \frac{Q_{\text{bid}} - Q_{\text{ask}}}{Q_{\text{bid}} + Q_{\text{ask}}}
\]

to emit a value between -1 and +1. Large positive readings indicate bid-side
dominance while negative readings indicate sell pressure.

## Logistic Weight Node

Real order books whipsaw constantly, so the linear ratio reacts too aggressively
to fleeting depth changes. `logistic_order_book_imbalance_node` maps the
imbalance through a sigmoid and outputs a weight `w ∈ [0, 1]`.

- `slope` controls how quickly the sigmoid saturates. Higher values converge to
  0/1 close to the origin.
- `clamp` bounds the imbalance (by absolute value) before applying the sigmoid
  and keeps thin-book spikes in check.
- `offset` shifts the centre of the sigmoid when a different neutral point is
  required.

## Micro-Price Node

`micro_price_node` combines the best quotes (`best_bid`, `best_ask`) with a
weight node to compute

\[
P_{\text{micro}} = w\,P_{\text{ask}} + (1 - w)\,P_{\text{bid}}.
\]

You can supply a pre-computed weight or pass an imbalance node and select the
`mode` (`"linear"` or `"logistic"`) to derive it on the fly.

## Example Code

```python
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.transforms import (
    order_book_imbalance_node,
    logistic_order_book_imbalance_node,
    micro_price_node,
)

bid_volume = SourceNode(interval="1s", period=1, config={"id": "bid_volume"})
ask_volume = SourceNode(interval="1s", period=1, config={"id": "ask_volume"})
best_bid = SourceNode(interval="1s", period=1, config={"id": "best_bid"})
best_ask = SourceNode(interval="1s", period=1, config={"id": "best_ask"})

imbalance = order_book_imbalance_node(bid_volume, ask_volume)
logistic_weight = logistic_order_book_imbalance_node(
    bid_volume,
    ask_volume,
    slope=4.0,
    clamp=0.8,
)
micro_price = micro_price_node(best_bid, best_ask, weight_node=logistic_weight)
```

## Tuning Guide

- Start with **slope** between 2 and 6 and validate the predictive lift through
  backtests.
- Keep **clamp** near ±0.7–0.9. Lower values remove too much information, while
  higher values reintroduce noise.
- Choose `mode="linear"` when the raw depth ratio is desired. Logistic mode is
  the default and performs well in high-volatility venues.
- Reuse the logic in other alpha features by calling the shared
  `imbalance_to_weight()` helper.
