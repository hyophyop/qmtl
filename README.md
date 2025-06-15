# qmtl

QMTL orchestrates trading strategies as directed acyclic graphs (DAGs). The gateway forwards DAGs to the DAG manager to deduplicate and schedule computations, while the SDK enables building reusable nodes for local or distributed execution. See [architecture.md](architecture.md) for full details.

## Installation

Set up a fresh environment using [uv](https://github.com/astral-sh/uv) and
install development dependencies:

```bash
uv venv
uv pip install -e .[dev]
```

These commands match the steps in the SDK tutorial
([docs/sdk_tutorial.md](docs/sdk_tutorial.md)) lines 5&ndash;18, where optional
extras are also documented:

```bash
uv pip install -e .[indicators]
uv pip install -e .[streams]
uv pip install -e .[generators]
uv pip install -e .[transforms]
```

## End-to-End Testing

For instructions on spinning up the entire stack and running the e2e suite, see [docs/e2e_testing.md](docs/e2e_testing.md).

## Running the Test Suite

Run all unit and integration tests with:

```bash
uv run pytest -q tests
```

## Running Services

Start the gateway HTTP server and interact with the DAG manager using the
provided CLI tools.

```bash
qmtl-gateway --redis-dsn redis://localhost:6379 \
             --postgres-dsn postgresql://localhost/qmtl

# submit a DAG diff
qmtl-dagm diff --file dag.json --target localhost:50051
```

See [gateway.md](gateway.md) and [dag-manager.md](dag-manager.md) for more
information on configuration and advanced usage.

## SDK Tutorial

For instructions on implementing strategies with the SDK, see
[docs/sdk_tutorial.md](docs/sdk_tutorial.md).

## Backfills

[docs/backfill.md](docs/backfill.md) explains how to preload historical data by
injecting `HistoryProvider` instances
into `StreamInput` nodes. This also covers persisting data via `EventRecorder`.
[docs/backfill.md](docs/backfill.md).

### QuestDBLoader with a custom fetcher

`QuestDBLoader` can pull missing rows from any async source. Implement a
`DataFetcher` and pass it to the loader:

```python
import httpx
import pandas as pd
from qmtl.sdk import DataFetcher, QuestDBLoader

class BinanceFetcher:
    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        url = (
            "https://api.binance.com/api/v3/klines"
            f"?symbol={node_id}&interval={interval}m"
            f"&startTime={start * 1000}&endTime={end * 1000}"
        )
        async with httpx.AsyncClient() as client:
            data = (await client.get(url)).json()
        rows = [
            {"ts": int(d[0] / 1000), "open": float(d[1]), "close": float(d[4])}
            for d in data
        ]
        return pd.DataFrame(rows)

fetcher = BinanceFetcher()
loader = QuestDBLoader(
    "postgresql://user:pass@localhost:8812/qdb",
    fetcher=fetcher,
)
```

