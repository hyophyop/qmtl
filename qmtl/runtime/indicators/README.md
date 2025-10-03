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
top ``levels`` tiers. Pass ``period`` to control how many recent outputs the
node retains in its cache. The helper also exposes
`order_book_obi_ema(..., ema_period=20)` which applies an exponential moving
average to the raw OBI stream for smoother downstream consumption and ensures
the underlying OBI cache keeps ``ema_period`` samples available.

For deeper liquidity cues, `order_book_imbalance_levels` computes the
"multi-level" imbalance (also expressed as `(bid-ask)/(bid+ask)` but using a
configurable number of tiers) while `order_book_depth_slope` estimates the
internal depth gradient on each side of book via a simple linear regression of
cumulative size against the level index. Empty books (or tiers with malformed
data) safely resolve to `0.0` slopes and an `OBI_L` of `0.0`, allowing
downstream features to remain finite. Both helpers accept a ``period`` argument
to retain additional history in their caches.

`order_book_obiL_and_slope` wraps both metrics and emits a mapping with
``{"obi_l": float, "bid_slope": float, "ask_slope": float}`` so downstream
nodes can subscribe to a single feed.

```python
from qmtl.runtime.indicators import (
    order_book_obi,
    order_book_obi_ema,
    order_book_imbalance_levels,
    order_book_depth_slope,
    order_book_obiL_and_slope,
)

obi = order_book_obi(book_snapshots, levels=3)
smoothed = order_book_obi_ema(book_snapshots, levels=3, ema_period=10)
obi_l = order_book_imbalance_levels(book_snapshots, levels=5)
depth_profile = order_book_depth_slope(book_snapshots, levels=5)
combined = order_book_obiL_and_slope(book_snapshots, levels=5)
```

> **Note:** When the book snapshot is missing altogether the nodes emit
> `None` to signal upstream data gaps.

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

