# Multi-asset factor DAG patterns

Guidance on data shapes and node layout for cross-sectional factors. The goal (issue #1651) is to reduce boilerplate when aligning multiple symbols in a DAG.

## 1) Choose a data shape

- **Tall (recommended default):** each row carries `symbol`. Example: `{"ts": ..., "symbol": "BTCUSDT", "close": 100}`.  
  - Pros: StreamInputs stay simple per symbol; adding symbols rarely changes the DAG shape.  
  - Cons: factor nodes need a pivot/group step.
- **Wide (small universes only):** a row contains many symbol fields. Example: `{"ts": ..., "close": {"BTC": 100, "ETH": 10}}` or `{"close_BTC": 100, "close_ETH": 10}`.  
  - Pros: no pivot needed.  
  - Cons: snapshot size grows quickly; adding symbols forces schema/code changes.

### Recommendation
- Keep price/volume inputs as **per-symbol StreamInputs** (tall) and pivot only where needed in factor nodes.
- Wide is acceptable for tiny universes (≈ <5 symbols), but prefer tall for scalability.

## 2) CacheView patterns

Use `CacheView.window()` / `CacheWindow` to cut down the list→DataFrame pivot boilerplate. (See [cacheview_helpers.md](./cacheview_helpers.md))

```python
from qmtl.runtime.sdk import CacheView
import numpy as np
import polars as pl

UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

def compute(view: CacheView):
    frames = []
    for sym in UNIVERSE:
        win = view.window(f"px:{sym}", 60, count=200)
        frame = win.as_frame()
        if frame.is_empty():
            continue
        frame = frame.with_columns(pl.lit(sym).alias("symbol"))
        frames.append(frame.select(["ts", "symbol", "close"]))

    if not frames:
        return None

    tall = pl.concat(frames).sort("ts")
    wide = tall.pivot(values="close", index="ts", columns="symbol")
    returns = wide.select(pl.all().pct_change()).drop_nulls()

    if "baseline" not in returns.columns:
        return None
    cov = np.cov(returns.to_numpy(), rowvar=False)
    cols = returns.columns
    idx = cols.index("baseline")
    var_b = cov[idx, idx]
    betas = (
        {col: cov[cols.index(col), idx] / var_b for col in cols}
        if var_b
        else None
    )
    return {"beta": betas}
```

- Use `count=` to keep window size bounded.
- Be defensive about missing symbols; empty frames shouldn’t explode the node.

## 3) DAG layout (conceptual)

- StreamInput: `px:{symbol}` (price), plus `vol:{symbol}` etc. as needed.
- Factor node(s):
  - Stage 1: collect price/volume windows and align/pivot (via `CacheView.window`).
  - Stage 2: compute cross-sectional factor (betas, spreads, baskets, etc.).
  - Stage 3: optionally fan out to per-symbol signals or to portfolio/risk nodes.
- Store/artifacts: if the pivoted matrix is large, publish/store intermediates to avoid recomputing.

## 4) History/backfill considerations

- Cross-sectional factors rely on aligned time axes; set `history_start`/`history_end` or configure SeamlessDataProvider to deliver matched coverage per symbol.
- Decide how to treat gaps: drop missing symbols, or `dropna=False` before alignment and handle NaNs explicitly.

## 5) Checklist

- [ ] Inputs stay tall where possible so symbols can be added without DAG rewrites.
- [ ] `CacheView.window(..., count=...)` bounds window length.
- [ ] Missing symbols/rows handled defensively.
- [ ] Factor output schema documents how symbols are encoded (dict/matrix).
