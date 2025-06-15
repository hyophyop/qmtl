# Backfilling Historical Data

This guide explains how to populate node caches with past values before a strategy starts processing live data.

## Configuring a HistoryProvider

A `HistoryProvider` supplies historical data for a `(node_id, interval)` pair. It
must implement the `fetch(start, end, *, node_id, interval)` method and return a
`pandas.DataFrame` where each row contains a timestamp column `ts` and any
payload fields.  Advanced providers can optionally expose:

- `coverage(node_id, interval)` returning a list of `(start, end)` timestamp
  ranges already present in the underlying store.
- `fill_missing(start, end, node_id, interval)` instructing the provider to
  populate gaps within the given range.

In some cases a provider may rely on a separate **DataFetcher** object to
retrieve missing rows.  A `DataFetcher` exposes a single asynchronous
`fetch(start, end, *, node_id, interval)` method returning the same frame
structure.  When a provider is created without a fetcher, calling
`fill_missing` will raise a `RuntimeError`.

The SDK ships with `QuestDBLoader` which reads from a QuestDB instance:

```python
from qmtl.sdk import QuestDBLoader

source = QuestDBLoader("postgresql://user:pass@localhost:8812/qdb")

# with an external fetcher supplying missing rows
# fetcher = MyFetcher()
# source = QuestDBLoader(
#     "postgresql://user:pass@localhost:8812/qdb",
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
    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        url = (
            "https://api.binance.com/api/v3/klines"
            f"?symbol={node_id}&interval={interval}m"
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
    "postgresql://user:pass@localhost:8812/qdb",
    fetcher=fetcher,
)
```

Custom providers can implement `HistoryProvider` or provide an object with the same interface.

### Injecting into `StreamInput`

Historical data and event recording can be supplied when creating a `StreamInput`:

```python
from qmtl.sdk import StreamInput, QuestDBLoader, QuestDBRecorder

stream = StreamInput(
    interval=60,
    history_provider=QuestDBLoader(
        "postgresql://user:pass@localhost:8812/qdb",
        fetcher=fetcher,
    ),
    start=1700000000,
    end=1700003600,
    event_recorder=QuestDBRecorder("postgresql://user:pass@localhost:8812/qdb"),
)
```

## Running a Backfill

Backfills can be triggered when executing a strategy through the CLI or the `Runner` API. Provide the source specification along with the timestamp range:

```bash
python -m qmtl.sdk tests.sample_strategy:SampleStrategy \
       --mode dryrun \
       --gateway-url http://localhost:8000 \
       --backfill-source questdb:postgresql://user:pass@localhost:8812/qdb \
       --backfill-start 1700000000 --backfill-end 1700003600
```

The same operation via Python code:

```python
from qmtl.sdk import Runner
from tests.sample_strategy import SampleStrategy

Runner.dryrun(
    SampleStrategy,
    gateway_url="http://localhost:8000",
    backfill_source="questdb:postgresql://user:pass@localhost:8812/qdb",
    backfill_start=1700000000,
    backfill_end=1700003600,
)
```

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

