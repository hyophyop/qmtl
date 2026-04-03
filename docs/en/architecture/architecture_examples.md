---
title: "QMTL Architecture Examples"
tags: [architecture, examples]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# QMTL Architecture Examples

This page collects non-normative examples that were split out of the main [QMTL Normative Architecture](architecture.md). Normative service boundaries still live in the architecture spec, while runtime checklists and operational guidance live in [Architecture Runtime Reliability](../reference/architecture_runtime_reliability.md).

## 1. General strategy example (Runner API)

This sample shows the baseline pattern: user-defined compute functions, direct node references inside the DAG, and warmup rules derived from `interval` and `period`.

```python
from qmtl.runtime.sdk import Strategy, Node, StreamInput, Runner
import polars as pl


class GeneralStrategy(Strategy):
    def setup(self):
        price_stream = StreamInput(
            interval="60s",
            period=30,
        )

        def generate_signal(view) -> pl.DataFrame:
            price = view.as_frame(price_stream, 60, columns=["close"]).validate_columns(["close"])
            momentum = price.frame.get_column("close").pct_change().rolling_mean(window_size=5)
            signal = (momentum > 0).cast(pl.Int64)
            return pl.DataFrame({"signal": signal})

        signal_node = Node(
            input=price_stream,
            compute_fn=generate_signal,
            name="momentum_signal",
        )

        self.add_nodes([price_stream, signal_node])


if __name__ == "__main__":
    Runner.submit(GeneralStrategy, world="general_demo")
```

## 2. Seamless Data Provider on-ramp

Seamless Data Provider is the single entry for history, backfill, and live data reads. Strategy code stays focused on `StreamInput` declarations and node logic; the world data preset plus Seamless preset map decide which concrete providers are wired.

- Runtime baseline: `qmtl/runtime/sdk/seamless_data_provider.py`
- Conformance/schema normalization: `qmtl/runtime/sdk/conformance.py`
- Single-flight backfill coordination: `qmtl/runtime/sdk/backfill_coordinator.py`
- SLA rails: `qmtl/runtime/sdk/sla.py`

See [World Data Preset Contract](../world/world_data_preset.md) and [Seamless Data Provider v2](seamless_data_provider_v2.md) for the actual contract.

## 3. TagQuery strategy example

`TagQueryNode` avoids hard-coding queue names. Instead, it resolves all upstream queues that match a tag set and interval at runtime.

```python
from qmtl.runtime.sdk import Strategy, Node, Runner, TagQueryNode, MatchMode
import polars as pl


def calc_corr(view) -> pl.DataFrame:
    aligned = view.align_frames([(node_id, 3600) for node_id in view], window=24)
    frames = [frame.frame for frame in aligned if not frame.frame.is_empty()]
    if not frames:
        return pl.DataFrame()

    corr = pl.concat(frames, how="horizontal").corr()
    return corr


class CorrelationStrategy(Strategy):
    def setup(self):
        indicators = TagQueryNode(
            query_tags=["ta-indicator"],
            interval="1h",
            period=24,
            match_mode=MatchMode.ANY,
            compute_fn=calc_corr,
        )

        corr_node = Node(
            input=indicators,
            compute_fn=calc_corr,
            name="indicator_corr",
        )

        self.add_nodes([indicators, corr_node])


if __name__ == "__main__":
    Runner.submit(CorrelationStrategy, world="corr_demo")
```

Summary:

1. Runner asks Gateway `GET /queues/by_tag` through `TagQueryManager`.
2. Gateway returns the matching queue set based on the global DAG and namespace policy.
3. SDK synthesizes a read-only `CacheView` across those queues and passes it into `compute_fn`.
4. Newly discovered queues can be added at runtime without editing the strategy.

Routing rules live in [World Data Preset Contract](../world/world_data_preset.md) and [DAG Manager](dag-manager.md).

## 4. Cross-market strategy example

This pattern combines upstreams from different markets while keeping the same `Runner.submit(..., world=...)` surface.

```python
from qmtl.runtime.sdk import Strategy, Node, StreamInput, Runner
import polars as pl


def lagged_corr(view) -> pl.DataFrame:
    btc = pl.DataFrame([v for _, v in view[btc_price][60]])
    mstr = pl.DataFrame([v for _, v in view[mstr_price][60]])
    btc_shift = btc.get_column("close").shift(90)
    corr = btc_shift.pearson_corr(mstr.get_column("close"))
    return pl.DataFrame({"lag_corr": [corr]})


class CrossMarketLagStrategy(Strategy):
    def setup(self):
        btc_price = StreamInput(tags=["BTC", "price", "binance"], interval="60s", period=120)
        mstr_price = StreamInput(tags=["MSTR", "price", "nasdaq"], interval="60s", period=120)

        corr_node = Node(
            input=[btc_price, mstr_price],
            compute_fn=lagged_corr,
            name="btc_mstr_corr",
        )

        self.add_nodes([btc_price, mstr_price, corr_node])


Runner.submit(CrossMarketLagStrategy, world="cross_market_lag")
```

Key points:

- Inputs can come from one market while trading decisions target another.
- The world still owns evaluation, activation, and order gating.
- Strategy code handles only market-specific data logic; promotion and safe fallback remain backend responsibilities.

{{ nav_links() }}
