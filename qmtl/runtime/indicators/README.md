# qmtl.runtime.indicators

Common technical indicator nodes for the QMTL SDK.

- Modules observe the Single Responsibility Principle and keep dependencies minimal.
- When adding new indicators, include unit tests under `tests/`.

The indicators module ships with the core package; no extra install is required.

Use with:

```python
from qmtl.runtime.indicators import sma
from qmtl.runtime.indicators import acceptable_price_band_node
```

## Order-book imbalance (OBI)

`order_book_obi` consumes raw order-book snapshots containing bid and ask
levels and returns the normalized imbalance `(bid-ask)/(bid+ask)` across the
top ``levels`` tiers. The helper also exposes
`order_book_obi_ema(..., ema_period=20)` which applies an exponential moving
average to the raw OBI stream for smoother downstream consumption.

```python
from qmtl.runtime.indicators import order_book_obi, order_book_obi_ema

obi = order_book_obi(book_snapshots, levels=3)
smoothed = order_book_obi_ema(book_snapshots, levels=3, ema_period=10)
```

## Acceptable price band alpha

`acceptable_price_band_node` adapts a dynamic mean and volatility band using
`FourDimCache` for historical averages. It returns updated band statistics and a
nonlinear alpha value combining momentum and mean-reversion effects driven by
price overshoots and volume surprises.

## Custom indicators with history

Wrap any function returning an ``{"alpha": value}`` mapping with
``alpha_indicator_with_history`` to keep a sliding window of recent alpha
values:

```python
from qmtl.runtime.indicators import alpha_indicator_with_history

def my_alpha(view):
    return {"alpha": 42}

node = alpha_indicator_with_history(my_alpha, window=30)
```

The resulting node emits a list of the latest ``window`` alpha values.

