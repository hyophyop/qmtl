# Backfilling Historical Data

This guide explains how to populate node caches with past values before a strategy starts processing live data.

## Configuring a CacheLoader

A `CacheLoader` provides historical data for a `(node_id, interval)` pair. It must implement the `fetch(start, end, *, node_id, interval)` method and return a `pandas.DataFrame` where each row contains a timestamp column `ts` and any payload fields.

The SDK ships with `QuestDBLoader` which reads from a QuestDB instance:

```python
from qmtl.sdk import QuestDBLoader

source = QuestDBLoader("postgresql://user:pass@localhost:8812/qdb")
```

Custom loaders can implement `CacheLoader` or provide an object with the same interface.

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

