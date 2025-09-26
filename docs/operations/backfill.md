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
- `ensure_range(start, end, *, node_id, interval)` which performs any automatic
  backfill the provider supports. When present the runtime will prefer this
  helper over manual coverage checks.

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

The SDK ships with `QuestDBHistoryProvider` which reads from a QuestDB instance:

```python
from qmtl.runtime.sdk import QuestDBHistoryProvider

source = QuestDBHistoryProvider(
    dsn="postgresql://user:pass@localhost:8812/qdb",
)

# with an external fetcher supplying missing rows
# fetcher = MyFetcher()
# source = QuestDBHistoryProvider(
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
from qmtl.runtime.sdk import DataFetcher

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
loader = QuestDBHistoryProvider(
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

## Auto Backfill Strategies

The SDK ships with :class:`AugmentedHistoryProvider`, a facade that wraps a
`HistoryBackend` and coordinates optional auto backfill helpers. When
constructed with an :class:`AutoBackfillStrategy`, the facade exposes
``ensure_range`` which populates missing data before history is fetched.  The
simplest strategy delegates to an existing :class:`DataFetcher`:

!!! note
    Every :class:`HistoryProvider` exposes an ``ensure_range`` helper. When a
    provider does not override it, the default implementation simply proxies to
    :meth:`fill_missing`, so adapters written before auto backfill support keep
    working unchanged.

```python
from qmtl.runtime.sdk import AugmentedHistoryProvider, FetcherBackfillStrategy
from qmtl.runtime.io import QuestDBBackend

backend = QuestDBBackend(dsn="postgresql://user:pass@localhost:8812/qdb")
provider = AugmentedHistoryProvider(
    backend,
    fetcher=my_fetcher,
    auto_backfill=FetcherBackfillStrategy(my_fetcher),
)

# ensure the warmup window is covered before loading
await provider.ensure_range(1700000000, 1700001800, node_id="BTC", interval=60)
frame = await provider.fetch(1700000000, 1700001860, node_id="BTC", interval=60)
```

``FetcherBackfillStrategy`` computes coverage gaps, delegates each gap to the
fetcher, writes the normalized rows back to the backend and refreshes cached
coverage metadata. Other strategies such as
``LiveReplayBackfillStrategy`` can ingest live buffers instead of hitting an
external API.

### Injecting into `StreamInput`

Historical data and event recording can be supplied when creating a `StreamInput`:

```python
from qmtl.runtime.sdk import (
    StreamInput,
    QuestDBHistoryProvider,
    QuestDBRecorder,
    EventRecorderService,
)

stream = StreamInput(
    interval="60s",
    history_provider=QuestDBHistoryProvider(
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

When the QuestDB history provider (also exported as ``QuestDBLoader`` for
backwards compatibility) or recorder is created without a ``table`` argument it
automatically uses ``stream.node_id`` as the table name.  Pass ``table="name"``
explicitly to override this behaviour.

``StreamInput`` binds the provider and recorder service during construction and
then treats them as read-only. Attempting to modify ``history_provider`` or
``event_service`` after creation will raise an ``AttributeError``.

## Distributed Coordinator Observability

Backfill workers that rely on the distributed coordinator should monitor the
structured lifecycle logs emitted by the SDK. Each successful transition now
produces a log entry under the `seamless.backfill` namespace:

```text
seamless.backfill.coordinator_claimed {"coordinator_id": "coordinator.local", "lease_key": "nodeA:60:1700:1760:world-1:2024-01-01T00:00:00Z", "node_id": "nodeA", "interval": 60, "batch_start": 1700, "batch_end": 1760, "world": "world-1", "requested_as_of": "2024-01-01T00:00:00Z", "worker": "worker-42", "lease_token": "abc", "lease_until_ms": 2000, "completion_ratio": 0.5}
```

Three events are emitted:

- `seamless.backfill.coordinator_claimed` – a worker successfully acquired a lease.
- `seamless.backfill.coordinator_completed` – a backfill window finished and the lease was released cleanly.
- `seamless.backfill.coordinator_failed` – a lease was failed intentionally (for example when a backfill attempt raises).

All events carry the fields called out in the operations checklist:

- **`coordinator_id`** – derived from the distributed coordinator URL host.
- **`lease_key`** – the canonical lease identifier (`node:interval:start:end:world:requested_as_of`).
- **`node_id`**, **`interval`**, **`batch_start`**, **`batch_end`** – partition identifiers that drive dashboards.
- **`world`** and **`requested_as_of`** – present when the request context supplies world governance metadata.
- **`worker`** – populated from `QMTL_SEAMLESS_WORKER`, `QMTL_WORKER_ID`, or the container hostname; configure one of the environment variables in production to keep dashboards consistent.
- **`lease_token`** and **`lease_until_ms`** – useful when recovering stuck leases via `scripts/lease_recover.py`.
- **`completion_ratio`** – mirrors the gauge recorded in Prometheus to track progress per lease.
- **`reason`** – included on the failed event to annotate why the lease was abandoned.

Dashboards in `operations/monitoring/seamless_v2.jsonnet` already chart
`backfill_completion_ratio`. Combine those panels with the lifecycle logs above
to understand which worker handled a batch and whether the lease progressed or
required manual recovery.

## Priming History for Warmup

When executing a strategy, the SDK ensures each `StreamInput` has enough history
to satisfy its `period × interval` warmup window. For providers that implement
`ensure_range()`, auto backfill occurs before any gaps are inspected. Providers
without that helper fall back to the `coverage()` plus `fill_missing()` loop so
existing adapters continue to work.

Both :func:`Runner.run` and :func:`Runner.offline` execute the same warmup
pipeline: ranges are reconciled via the provider, the `BackfillEngine` fetches
rows into the node caches and the runtime replays those events through the
strategy graph. This guarantees that local dry runs exercise the identical
bootstrap logic used in production.

Integrated run (world‑driven):

```python
from qmtl.runtime.sdk import Runner
from tests.sample_strategy import SampleStrategy

Runner.run(
    SampleStrategy,
    world_id="sample_world",
    gateway_url="http://localhost:8000",
)
```

Offline priming for local testing:

```python
from qmtl.runtime.sdk import Runner
from tests.sample_strategy import SampleStrategy

Runner.offline(SampleStrategy)
```

During execution the SDK collects cached history and replays it through the
`Pipeline` in timestamp order to initialize downstream nodes. If Ray execution
is enabled, compute functions may run concurrently during this replay phase.

## Monitoring Progress

Backfill operations emit Prometheus metrics via `qmtl.runtime.sdk.metrics`:

- `backfill_jobs_in_progress`: number of active jobs
- `backfill_last_timestamp{node_id,interval}`: latest timestamp successfully backfilled
- `backfill_retry_total{node_id,interval}`: retry attempts
- `backfill_failure_total{node_id,interval}`: total failures

Start the metrics server to scrape these values:

```python
from qmtl.runtime.sdk import metrics

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
from qmtl.runtime.sdk import StreamInput

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
