# History Data Quickstart

This guide shows how to attach your own historical data to QMTL strategies
without reverse‑engineering the history warm‑up machinery. It is aimed at
strategy repositories that:

- run locally with `Runner.offline(...)` during development, and/or
- run under WorldService using `Runner.run(...)` for backtests or live trials.

The recommended surface for new integrations is the **Seamless Data Provider**
layer. The lower‑level `HistoryProvider` interface still exists for backwards
compatibility but should be treated as an advanced extension point.

## How history flows into strategies

- Strategies declare upstream time series via `StreamInput` nodes.
- The SDK populates node caches during warm‑up using
  `HistoryWarmupService` and `BackfillEngine`.
- Strategies read data through `CacheView` in their `compute_fn` implementations.

In modern setups, you plug data into this flow by wiring a
`SeamlessDataProvider` (or a concrete subclass such as
`EnhancedQuestDBProvider`) into your `StreamInput` nodes.

For the underlying architecture, see:

- [`design/seamless_data_provider.md`](../design/seamless_data_provider.md)
- [`architecture/seamless_data_provider_v2.md`](../architecture/seamless_data_provider_v2.md)

## Wiring a Seamless provider into a stream

The simplest way to attach external history is to use
`EnhancedQuestDBProvider` with a `DataFetcher` implementation that knows how
to load your data (CSV, Parquet, HTTP, internal APIs, etc.).

```python
import pandas as pd

from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy
from qmtl.runtime.sdk import StreamInput, ProcessingNode, Strategy, Runner


class ExampleMarketDataFetcher:
    async def fetch(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
    ) -> pd.DataFrame:
        # Replace this stub with your own loader
        ts = list(range(start, end, interval))
        return pd.DataFrame(
            {
                "ts": ts,
                "price": [100.0 + i * 0.01 for i in range(len(ts))],
            }
        )


class MyStrategy(Strategy):
    def setup(self) -> None:
        provider = EnhancedQuestDBProvider(
            dsn="postgresql://localhost:8812/qmtl",
            table="my_prices",
            fetcher=ExampleMarketDataFetcher(),
            strategy=DataAvailabilityStrategy.SEAMLESS,
        )

        src = StreamInput(
            tags=["price:BTC/USDT:1m"],
            interval="60s",
            period=500,
            history_provider=provider,
        )

        def compute(view):
            series = view[src][60]
            ts, row = series.latest()
            return row["price"]

        node = ProcessingNode(
            input=src,
            compute_fn=compute,
            name="price_node",
            interval="60s",
            period=500,
        )
        self.add_nodes([src, node])
```

Key points:

- `EnhancedQuestDBProvider` is a concrete `SeamlessDataProvider` subclass that
  already implements the `fetch`, `coverage`, and `fill_missing` methods
  expected by the warm‑up layer.
- Your `DataFetcher` only needs to return a `DataFrame` with a `ts` column;
  the provider takes care of coverage, auto‑backfill, and conformance.
- `StreamInput(history_provider=provider)` is the only wiring change needed in
  the strategy.

More end‑to‑end examples live in
`examples/seamless_data_provider_examples.py`.

For small, file- or notebook-based experiments that do not use QuestDB, you
can instead use :class:`qmtl.runtime.io.InMemorySeamlessProvider` to bind
DataFrames or CSV files directly:

```python
from qmtl.runtime.io import InMemorySeamlessProvider


class MyStrategy(Strategy):
    def setup(self) -> None:
        provider = InMemorySeamlessProvider()

        src = StreamInput(interval="60s", period=500, tags=["price:BTC/USDT:1m"], history_provider=provider)

        # Load a local CSV once and register it as history for ``src``.
        provider.register_csv(src, "btc_usdt_1m.csv", ts_col="ts")

        def compute(view):
            series = view[src][60]
            ts, row = series.latest()
            return row["price"]

        node = ProcessingNode(
            input=src,
            compute_fn=compute,
            name="price_node",
            interval="60s",
            period=500,
        )
        self.add_nodes([src, node])
```

## Controlling the history window

Once a provider is wired in, you can control the history window used for
warm‑up in both online and offline modes, and optionally inject a Seamless
provider into an existing strategy without modifying its ``setup``.

- WorldService / Gateway runs:

  ```python
  Runner.run(
      MyStrategy,
      world_id="my-world",
      gateway_url="http://gateway",
      history_start=1700000000,  # inclusive, epoch seconds
      history_end=1700003600,    # inclusive upper bound used by warm-up service
  )
  ```

- Local offline runs:

  ```python
  Runner.offline(
      MyStrategy,
      history_start=1700000000,
      history_end=1700003600,
      # Optional: attach a Seamless provider to all StreamInput nodes
      # that do not already specify a history_provider.
      data=my_seamless_provider,
  )
  ```

If both `history_start` and `history_end` are `None`, the warm‑up service:

- falls back to a small baseline window in pure offline mode when no provider
  is configured, or
- derives an appropriate window from provider coverage and cached snapshots.

## HistoryProvider as an advanced contract

The lower‑level `HistoryProvider` ABC is still available at:

- `qmtl.runtime.sdk.data_io.HistoryProvider`

It underpins the warm‑up and backfill services, but typical strategy code
does **not** need to subclass it directly:

- Seamless providers such as `EnhancedQuestDBProvider` already satisfy the
  contract and expose richer behaviour (conformance, SLA enforcement,
  backfill coordination).
- Existing QuestDB integrations can continue to use
  `QuestDBHistoryProvider` / `QuestDBLoader` when the legacy contract is
  sufficient.

If you do need a custom `HistoryProvider`, use the Seamless design docs above
plus the tests under `tests/qmtl/runtime/sdk/` (for example
`test_history_components.py`) as a reference, and prefer wrapping a dedicated
storage backend rather than implementing warm‑up behaviour from scratch.
