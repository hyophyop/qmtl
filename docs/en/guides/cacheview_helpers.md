# CacheView helpers quickstart

`CacheView.window()` and `CacheWindow` turn cache snapshots into ready-to-use `DataFrame` / `Series` objects. They squash the common “view → list → DataFrame → column check” boilerplate called out in issue #1645.

## Basics

```python
from qmtl.runtime.sdk import CacheView
import polars as pl

def compute(view: CacheView):
    price_win = view.window("prices", 60, count=50)
    price_win.require_columns(["close", "volume"])

    frame = price_win.as_frame()  # includes ts, close, volume
    closes = price_win.to_series("close")
    returns = closes.pct_change().drop_nulls()
```

- `window(node, interval, count=N)` returns the latest N entries; `count=None` keeps the full window.
- For scalar payloads, `as_frame()` emits a `value` column by default.
- `require_columns([...])` surfaces missing columns early with a clear error.

## Align multiple inputs

```python
def compute(view: CacheView):
    asset = (
        view.window("asset_prices", 60, count=120)
        .as_frame()
        .select(["ts", "close"])
        .rename({"close": "asset"})
    )
    bench = (
        view.window("benchmark", 60, count=120)
        .as_frame()
        .select(["ts", "close"])
        .rename({"close": "bench"})
    )

    aligned = asset.join(bench, on="ts", how="inner").drop_nulls()
    returns = aligned.select(
        pl.col("asset").pct_change().alias("asset_ret"),
        pl.col("bench").pct_change().alias("bench_ret"),
    ).drop_nulls()

    cov = returns.select(pl.cov("asset_ret", "bench_ret")).item()
    var = returns.get_column("bench_ret").var()
    beta = cov / var if var else None
    return {"beta": beta}
```

- Use a join on the `ts` column to align frames when combining multiple inputs.
- Use `to_series(..., dropna=False)` when you want to preserve gaps before alignment.

## Scalars and empty windows

- Empty windows return an empty DataFrame from `as_frame()` and `None` from `latest()`.
- Requests like `count=0` are treated as an empty window without raising.
