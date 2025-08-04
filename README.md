# qmtl

QMTL orchestrates trading strategies as directed acyclic graphs (DAGs). The gateway forwards DAGs to the DAG manager to deduplicate and schedule computations, while the SDK enables building reusable nodes for local or distributed execution. See [architecture.md](architecture.md) for full details.

Use the DAG manager CLI to preview DAG structures:

```bash
qmtl dagm diff --file dag.json --dry-run
```

The JSON output can be rendered with tools like Graphviz for visual inspection. See [docs/templates.md](docs/templates.md) for diagrams of the built-in strategy templates.

## Installation

Set up a fresh environment using [uv](https://github.com/astral-sh/uv) and
install development dependencies:

```bash
uv venv
uv pip install -e .[dev]
```

These commands match the steps in the SDK tutorial
([docs/sdk_tutorial.md](docs/sdk_tutorial.md)).

Install the `io` extra if you need additional data modules:

```bash
uv pip install -e .[io]
```

## Project Initialization

Create a new working directory with `qmtl init`. The command generates a
project scaffold containing extension packages and a sample strategy.
Use `--strategy` to select from the built-in templates, `--list-templates` to
see the choices and `--with-sample-data` to copy an example OHLCV CSV and
notebook:

```bash
qmtl init --path my_qmtl_project
# list available templates
qmtl init --list-templates

# create project with the branching template
qmtl init --path my_qmtl_project --strategy branching
# include sample data
qmtl init --path my_qmtl_project --with-sample-data
cd my_qmtl_project
```

See [docs/templates.md](docs/templates.md) for a description of each template.

The scaffold includes empty `generators/`, `indicators/` and
`transforms/` packages for adding your own extensions.

Run the default strategy to verify everything is set up correctly:

```bash
python strategy.py
```

See `qmtl/examples/README.md` for additional strategies that can be executed
in the same way. A more detailed walkthrough from project creation to
testing is available in [docs/strategy_workflow.md](docs/strategy_workflow.md).


## Development Workflow

Here’s a short workflow summary based on the repository’s guidelines:

1. **Environment Setup** – Use the `uv` tool and install dependencies in editable mode:

   ```bash
   uv pip install -e .[dev]
   ```

   This command ensures all development dependencies are available.

2. **Testing** – Run the tests via `uv` before committing:

   ```bash
   uv run -m pytest
   ```

   Commit only after tests pass.

3. **Design Approach** – Follow the Single Responsibility Principle (SRP) when designing modules and classes. This keeps features modular and easier to maintain.

For additional rules—such as adhering to architecture documents or managing distributable wheels—refer to [AGENTS.md](AGENTS.md) in the project root for the full guidelines.

## Coding Style

Use consistent naming for connection strings across the project. Prefer the `*_dsn` suffix for all connection parameters (for example `redis_dsn`, `database_dsn`, `neo4j_dsn`, `kafka_dsn`). Avoid one-letter variable names except in short loops; use descriptive names like `redis_client` or `dag_manager`.

## Optional Modules

Install additional functionality on demand:

- [Indicators](qmtl/indicators/README.md)
- [IO](qmtl/io) &mdash; `pip install qmtl[io]`
- [Generators](qmtl/generators/README.md)
- [Transforms](qmtl/transforms/README.md)


## End-to-End Testing

Bring up the stack with Docker Compose:

```bash
docker compose -f tests/docker-compose.e2e.yml up -d
```

Run the tests using uv:

```bash
uv run -m pytest tests/e2e
```

See [docs/e2e_testing.md](docs/e2e_testing.md) for the full guide.

## Running the Test Suite

Run all unit and integration tests with:

```bash
uv run -m pytest
```

## Monitoring

Load the sample alert definitions from `alert_rules.yml` into Prometheus to enable basic monitoring. For a full list of available alerts and Grafana dashboards, see [docs/monitoring.md](docs/monitoring.md).

## Running Services

Start the Gateway and DAG manager using the combined configuration file or rely
on the built-in defaults. Without ``--config`` both services start in a local
mode that uses SQLite and in-memory repositories. The sample ``qmtl.yml`` file
demonstrates how to switch to Postgres, Neo4j and Kafka for production.

```bash

# start the gateway HTTP server
qmtl gw --config qmtl/examples/qmtl.yml

# start the DAG manager
qmtl dagmgr-server --config qmtl/examples/qmtl.yml

# submit a DAG diff
qmtl dagm diff --file dag.json --target localhost:50051
```

Customize the sample YAML files in `qmtl/examples/` to match your environment.

See [gateway.md](gateway.md) and [dag-manager.md](dag-manager.md) for more
information on configuration and advanced usage.

## SDK Tutorial

For instructions on implementing strategies with the SDK, see
[docs/sdk_tutorial.md](docs/sdk_tutorial.md).

## Example Strategies

Run the samples inside the `qmtl/examples/` directory:

```bash
python -m qmtl.examples.general_strategy
python -m qmtl.examples.strategies.indicators_strategy
python -m qmtl.examples.transforms_strategy
python -m qmtl.examples.generators_example
python -m qmtl.examples.extensions_combined_strategy
```

Append `--with-ray` to enable Ray-based execution:

```bash
python -m qmtl.examples.general_strategy --with-ray
```

See [qmtl/examples/README.md](qmtl/examples/README.md) for additional scripts such as `tag_query_strategy.py` or `ws_metrics_example.py`.

## TagQuery Node Resolution

`TagQueryNode` instances no longer resolve queues themselves. The
`TagQueryManager.resolve_tags()` method retrieves queue mappings from the Gateway
and updates all registered nodes. `Runner` creates a manager automatically and
invokes this method in every mode, so manual calls are rarely needed.

`ProcessingNode` instances accept either a single upstream `Node` or a list of nodes via the `input` parameter. Dictionary inputs are no longer supported.

See [docs/faq.md](docs/faq.md) for common questions such as using `TagQueryNode` during backtesting.

## Backfills

[docs/backfill.md](docs/backfill.md) explains how to preload historical data by
injecting `HistoryProvider` instances
into `StreamInput` nodes. These dependencies must be provided at creation time
and cannot be reassigned later. The same guide covers persisting data via
`EventRecorder`.

Example injection:

```python
from qmtl.sdk import StreamInput, QuestDBLoader, QuestDBRecorder

stream = StreamInput(
    interval="60s",
    history_provider=QuestDBLoader(dsn="postgresql://user:pass@localhost:8812/qdb"),
    event_recorder=QuestDBRecorder(dsn="postgresql://user:pass@localhost:8812/qdb"),
)
```

``QuestDBLoader`` and ``QuestDBRecorder`` will default to using
``stream.node_id`` as the table name if ``table`` is not provided.

[docs/backfill.md](docs/backfill.md).

### QuestDBLoader with a custom fetcher

`QuestDBLoader` can pull missing rows from any async source. Implement a
`DataFetcher` and pass it to the loader:

```python
import httpx
import pandas as pd
from qmtl.sdk import DataFetcher, QuestDBLoader

class BinanceFetcher:
    async def fetch(self, start: int, end: int, *, node_id: str, interval: str) -> pd.DataFrame:
        url = (
            "https://api.binance.com/api/v3/klines"
            f"?symbol={node_id}&interval={interval}"
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
    dsn="postgresql://user:pass@localhost:8812/qdb",
    fetcher=fetcher,
)
```

