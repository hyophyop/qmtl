---
title: "Backfilling Historical Data"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# Backfilling Historical Data

This guide explains how to populate node caches with past values before a strategy starts processing live data.

## Configuring a HistoryProvider

A `HistoryProvider` supplies historical data for a `(node_id, interval)` pair. It
must implement an asynchronous
`fetch(start, end, *, node_id, interval)` method and return a `pandas.DataFrame`
where each row contains a timestamp column `ts` and any payload fields.  The
method signature mirrors that of :py:meth:`DataFetcher.fetch` which providers may
delegate to when retrieving rows from external services.  Advanced providers can
optionally expose asynchronous helpers:

- `coverage(node_id, interval)` returning a list of `(start, end)` timestamp
  ranges already present in the underlying store. This must be an
  asynchronous coroutine.
- `fill_missing(start, end, node_id, interval)` instructing the provider to
  populate gaps within the given range and is also a coroutine.

`coverage()` should return contiguous, inclusive ranges that already exist in
the storage backend. When `fill_missing()` is implemented the provider is
responsible for inserting real rows for any missing timestamps in a requested
range. A runner can use these APIs to determine what portions of history need to
be fetched or created before loading data into a strategy.

In some cases a provider may rely on a separate **DataFetcher** object to
retrieve missing rows.  A ``DataFetcher`` exposes a single **asynchronous**
``fetch(start, end, *, node_id, interval)`` coroutine returning the same frame
structure.  When a provider is created without a fetcher, calling
``fill_missing`` will raise a ``RuntimeError``.

The SDK ships with `QuestDBLoader` which reads from a QuestDB instance:

```python
from qmtl.sdk import QuestDBLoader

source = QuestDBLoader(
    dsn="postgresql://user:pass@localhost:8812/qdb",
)

# with an external fetcher supplying missing rows
# fetcher = MyFetcher()
# source = QuestDBLoader(
#     dsn="postgresql://user:pass@localhost:8812/qdb",
#     fetcher=fetcher,
# )
```

### Example `DataFetcher`

When historical rows are missing, the loader can query any external service.
Below is a minimal fetcher that reads candlesticks from Binance:

```python
import httpx
import pandas as pd
from qmtl.sdk import DataFetcher

class BinanceFetcher:
    async def fetch(self, start: int, end: int, *, node_id: str, interval: str) -> pd.DataFrame:
        url = (
            "https://api.binance.com/api/v3/klines"
            f"?symbol={node_id}&interval={interval}"
            f"&startTime={start * 1000}&endTime={end * 1000}"
        )
        async with httpx.AsyncClient() as client:
            data = (await client.get(url)).json()
        return pd.DataFrame(
            [
                {"ts": int(r[0] / 1000), "open": float(r[1]), "close": float(r[4])}
                for r in data
            ]
        )

fetcher = BinanceFetcher()
loader = QuestDBLoader(
    dsn="postgresql://user:pass@localhost:8812/qdb",
    fetcher=fetcher,
)
```

Custom providers can implement `HistoryProvider` or provide an object with the same interface.

An accompanying **EventRecorder** persists processed rows. A recorder must
implement the asynchronous ``persist(node_id, interval, timestamp, payload)``
method which receives each node payload exactly as emitted. Like providers,
recorders may implement ``bind_stream()`` to infer a table name from
``stream.node_id``.

When building custom providers or fetchers simply follow these method
signatures and return ``pandas.DataFrame`` objects with a ``ts`` column.
Subclasses are optional—any object adhering to the protocol works with the
SDK.

### Injecting into `StreamInput`

Historical data and event recording can be supplied when creating a `StreamInput`:

```python
from qmtl.sdk import StreamInput, QuestDBLoader, QuestDBRecorder, EventRecorderService

stream = StreamInput(
    interval="60s",
    history_provider=QuestDBLoader(
        dsn="postgresql://user:pass@localhost:8812/qdb",
        fetcher=fetcher,
    ),
    event_service=EventRecorderService(
        QuestDBRecorder(
            dsn="postgresql://user:pass@localhost:8812/qdb",
        )
    ),
)
```

When the QuestDB loader or recorder is created without a ``table`` argument it
automatically uses ``stream.node_id`` as the table name.  Pass ``table="name"``
explicitly to override this behaviour.

``StreamInput`` binds the provider and recorder service during construction and
then treats them as read-only. Attempting to modify ``history_provider`` or
``event_service`` after creation will raise an ``AttributeError``.

## Priming History for Warmup

When executing a strategy, the SDK ensures each `StreamInput` has enough history
to satisfy its `period × interval` warmup window. For providers that implement
`coverage()` and `fill_missing()`, the SDK uses them to backfill missing ranges
prior to loading history. This primes caches before computation continues.

Integrated run (world‑driven):

```python
from qmtl.sdk import Runner
from tests.sample_strategy import SampleStrategy

Runner.run(
    SampleStrategy,
    world_id="sample_world",
    gateway_url="http://localhost:8000",
)
```

Offline priming for local testing:

```python
from qmtl.sdk import Runner
from tests.sample_strategy import SampleStrategy

Runner.offline(SampleStrategy)
```

During execution the SDK collects cached history and replays it through the
`Pipeline` in timestamp order to initialize downstream nodes. If Ray execution
is enabled, compute functions may run concurrently during this replay phase.

## Monitoring Progress

Backfill operations emit Prometheus metrics via `qmtl.sdk.metrics`:

- `backfill_jobs_in_progress`: number of active jobs
- `backfill_last_timestamp{node_id,interval}`: latest timestamp successfully backfilled
- `backfill_retry_total{node_id,interval}`: retry attempts
- `backfill_failure_total{node_id,interval}`: total failures

Start the metrics server to scrape these values:

```python
from qmtl.sdk import metrics

metrics.start_metrics_server(port=8000)
```

Access `http://localhost:8000/metrics` while a backfill is running to observe its progress.

## BackfillEngine Internals

``BackfillEngine`` drives the asynchronous loading of history. Each job is
scheduled via :py:meth:`submit` which creates an ``asyncio`` task. The engine
tracks outstanding tasks in an internal set and :py:meth:`wait` gathers them
before returning. Jobs call ``HistoryProvider.fetch`` and merge the returned
rows into the node cache using
``NodeCache.backfill_bulk``. Completed timestamp ranges are recorded in
``BackfillState`` so subsequent calls can skip already processed data.

```python
from qmtl.sdk import StreamInput

stream = StreamInput(...)
await stream.load_history(start_ts, end_ts)
```

The ``load_history`` method shown above instantiates ``BackfillEngine``
internally and submits a single job for the configured provider. Failed fetches
are retried up to ``max_retries`` times with a short delay. During execution the
engine emits metrics such as ``backfill_jobs_in_progress``,
``backfill_last_timestamp``, ``backfill_retry_total`` and
``backfill_failure_total``.


{{ nav_links() }}
