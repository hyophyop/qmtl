# CCXT Seamless Data Provider Guide

Combining CCXT exchange data with QMTL's Seamless Data Provider yields a single
interface that handles auto backfill, live handoff, and coverage management.
This guide shows how to connect `CcxtOHLCVFetcher` to `EnhancedQuestDBProvider`
for immediate use in real strategies.

> See [CCXT × Seamless Integrated Architecture](../architecture/ccxt-seamless-integrated.md)
> for design background.

## Prerequisites

| Component | Purpose | How to prepare |
| --- | --- | --- |
| Python env | Install QMTL + ccxt extras | `uv pip install -e .[dev,ccxt,questdb]` |
| QuestDB | Historical store | `docker run -p 8812:8812 -p 9000:9000 questdb/questdb:latest` |
| (optional) Redis | Cluster rate limiting | `docker run -p 6379:6379 redis:7-alpine`; set `connectors.ccxt_rate_limiter_redis: redis://localhost:6379/0` (legacy `QMTL_CCXT_RATE_LIMITER_REDIS` supported) |
| CCXT API keys | Required for private endpoints/high QPS | Issue in exchange console; export `CCXT_APIKEY`, `CCXT_SECRET` |

## Core Components

1. **Backfill config** — `CcxtBackfillConfig` defines exchange, symbols, timeframe, paging.
2. **Data fetcher** — `CcxtOHLCVFetcher` collects OHLCV asynchronously via CCXT.
3. **Seamless provider** — `EnhancedQuestDBProvider` exposes auto backfill/cache/live under a single strategy interface.
4. **Live feed (optional)** — Attach `CcxtProLiveFeed` or a custom `LiveDataFeed` for realtime updates.

The following minimal example fetches 1‑minute candles. See the full script at
`examples/ccxt_seamless_provider.py`.

```python
import asyncio

from qmtl.runtime.io import CcxtBackfillConfig, CcxtOHLCVFetcher
from qmtl.runtime.io.seamless_provider import EnhancedQuestDBProvider
from qmtl.runtime.sdk.seamless_data_provider import DataAvailabilityStrategy

async def main() -> None:
    backfill = CcxtBackfillConfig(
        exchange="binance",           # CCXT exchange ID
        symbols=["BTC/USDT"],         # one or more symbols
        timeframe="1m",               # CCXT timeframe
        batch_limit=500,               # max candles per API call
        earliest_ts=1_577_836_800,     # optional lower bound (e.g., 2020-01-01 UTC)
    )
    fetcher = CcxtOHLCVFetcher(backfill)

    provider = EnhancedQuestDBProvider(
        dsn="postgresql://localhost:8812/qmtl",
        table="ohlcv",
        fetcher=fetcher,
        strategy=DataAvailabilityStrategy.SEAMLESS,
    )

    frame = await provider.fetch(
        start=1_706_745_600,  # 2024-01-01 00:00:00 UTC
        end=1_706_832_000,    # 2024-01-01 24:00:00 UTC
        node_id="ohlcv:binance:BTC/USDT:1m",
        interval=60,
    )
    print(frame.head())

if __name__ == "__main__":
    asyncio.run(main())
```

## Live Feed Integration

Attach `CcxtProLiveFeed` to receive realtime candle updates.

```python
from qmtl.runtime.io import CcxtProLiveFeed, CcxtProConfig

live_feed = CcxtProLiveFeed(
    CcxtProConfig(
        exchange="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
    )
)

provider = EnhancedQuestDBProvider(
    dsn="postgresql://localhost:8812/qmtl",
    table="ohlcv",
    fetcher=fetcher,
    live_feed=live_feed,
    strategy=DataAvailabilityStrategy.SEAMLESS,
)
```

The runtime processes data in the following order:

1. **Cache/Storage** — serve immediately if QuestDB has full coverage.
2. **Backfill** — fetch gaps from CCXT and load them into QuestDB.
3. **Live feed** — fill the newest candles from the feed when not yet materialized.

## Strategy/DAG Integration

Inject the provider into nodes that accept a `HistoryProvider`, such as `StreamInput`:

```python
from qmtl.runtime.sdk.nodes.sources import StreamInput

price = StreamInput(
    tags=["btc", "spot"],
    interval="60s",
    period=3600,
    history_provider=provider,
)
```

The provider automatically backfills in the background and enforces SLAs until
the DAG's requested window is fully covered. Enabling
`seamless.artifacts_enabled` in `qmtl.yml` writes parquet artifacts under
`~/.qmtl_seamless_artifacts/` to improve reproducibility during local work.

## Operations Checklist

- **Coverage checks**: call `provider.coverage(node_id=..., interval=...)` regularly to ensure QuestDB holds the requested window.
- **Monitoring**: deploy `operations/monitoring/seamless_v2.jsonnet` for dashboards such as `seamless_sla_deadline_seconds` and `seamless_conformance_flag_total`.
- **Rate limiting**: exchanges return 429 on policy violations. Tune `min_interval_ms` in `CcxtBackfillConfig` or configure Redis token buckets to back off properly.
- **Error reproduction**: set the same `seamless.coordinator_url` across workers to single‑flight backfills. Inspect `seamless.backfill.coordinator_*` events on contention.

## Troubleshooting FAQ

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `RuntimeError: ccxt is required ...` | Extras not installed | Re-run `uv pip install -e .[ccxt]` |
| QuestDB connection failure | DSN typo or server down | Verify DSN; check container/service health |
| Backfill never completes | Exchange rate limits exceeded | Reduce `batch_limit`, increase `min_interval_ms`, configure Redis token bucket |
| `seamless.sla.downgrade` warnings in DAG | SLA budget exceeded | Switch to `AUTO_BACKFILL` or shrink request windows |

## Further Reading

- `examples/ccxt_seamless_provider.py` – complete example
- [Seamless Migration to v2](seamless_migration_v2.md) – transition from the legacy history stack
- [CCXT × QuestDB (IO)](../io/ccxt-questdb.md) – QuestDB backend details and rate‑limit strategies
