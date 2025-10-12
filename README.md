<!-- markdownlint-disable MD012 MD013 MD025 -->

# qmtl

QMTL orchestrates trading strategies as directed acyclic graphs (DAGs). Its architecture is built around three components:

1. **Gateway** – accepts strategy submissions from SDKs and forwards DAGs to the DAG Manager for deduplication and scheduling.
2. **WorldService** – the single source of truth for policy and activation state.
3. **ControlBus** – an internal event bus bridged to clients through a tokenized WebSocket.

SDKs submit strategies through the Gateway, but activation and queue updates along with strategy file controls are delivered from the ControlBus via `/events/subscribe` over that WebSocket. See [architecture.md](docs/architecture/architecture.md) for full details.

Use the DAG Manager CLI to preview DAG structures:

```bash
qmtl service dagmanager diff --file dag.json --dry-run
```

Initialize a Neo4j database with the required constraints and indexes:

```bash
qmtl service dagmanager neo4j-init --uri bolt://localhost:7687 --user neo4j --password neo4j
```

Every subcommand now exposes its own help message. For example:

```bash
qmtl service --help
qmtl service gateway --help
qmtl service dagmanager --help
qmtl tools sdk --help
```

Use `service` for long-running daemons (Gateway, DAG Manager), `tools` for developer utilities such as the SDK runner, and `project` for scaffolding helpers. Legacy aliases like `qmtl gw` continue to function but emit deprecation warnings to ease migration.

The JSON output can be rendered with tools like Graphviz for visual inspection. See [docs/reference/templates.md](docs/reference/templates.md) for diagrams of the built-in strategy templates.

## Installation

Set up a fresh environment using [uv](https://github.com/astral-sh/uv) and
install development dependencies:

```bash
uv venv
uv pip install -e .[dev]
```

These commands match the steps in the SDK tutorial
([docs/guides/sdk_tutorial.md](docs/guides/sdk_tutorial.md)).

Install the `io` extra if you need additional data modules:

```bash
uv pip install -e .[io]
```

## Project Initialization

Create a new working directory with `qmtl project init`. The command generates a
project scaffold containing extension packages and a sample strategy.
Use `--strategy` to select from the built-in templates, `--list-templates` to
see the choices and `--with-sample-data` to copy an example OHLCV CSV and
notebook:

```bash
qmtl project init --path my_qmtl_project
# list available templates
qmtl project init --list-templates

# create project with the branching template
qmtl project init --path my_qmtl_project --strategy branching
# include sample data
qmtl project init --path my_qmtl_project --with-sample-data
cd my_qmtl_project
```

See [docs/reference/templates.md](docs/reference/templates.md) for a description of each template.

The scaffold includes empty `generators/`, `indicators/` and
`transforms/` packages for adding your own extensions, along with a
preconfigured `.gitignore` to keep temporary files out of version control.

Run the trade pipeline example to verify everything is set up correctly:

```bash
python -m qmtl.examples.strategy
```

See `qmtl/examples/README.md` for additional strategies that can be executed
in the same way. A more detailed walkthrough from project creation to
testing is available in [docs/guides/strategy_workflow.md](docs/guides/strategy_workflow.md).

## Quick Start (Validate → Export → Launch)

Bring services up in three steps. This mirrors the detailed guidance in
[Config CLI](docs/operations/config-cli.md) and [Backend Quickstart](docs/operations/backend_quickstart.md).

1. **Validate configuration** – catch missing sections or offline resources
   before booting services.

   ```bash
   uv run qmtl config validate --config qmtl/examples/qmtl.yml --offline
   ```

2. **Share the YAML with services** – keep the file in your workspace and pass
   it explicitly, or copy it to `./qmtl.yml` so CLIs discover it automatically.

   ```bash
   # Optional: make the sample config discoverable without extra flags.
   cp qmtl/examples/qmtl.yml ./qmtl.yml
   ```

3. **Launch services** – point both Gateway and DAG Manager at the same file.

   ```bash
   qmtl service gateway --config qmtl/examples/qmtl.yml
   qmtl service dagmanager server --config qmtl/examples/qmtl.yml
   ```

If the path is wrong or missing, the services log a warning and continue with
default settings—keep `qmtl config validate` in your workflow to catch typos
early.

## Trading Node Enhancements

Recent releases introduce several nodes for building realistic trading pipelines:

- **RiskManager** enforces position and portfolio limits. [Guide](docs/operations/risk_management.md) · [Example](qmtl/examples/strategies/risk_managed_strategy.py)
- **TimingController** validates market sessions and execution delays. [Guide](docs/operations/timing_controls.md) · [Example](qmtl/examples/strategies/timing_control_strategy.py)
- **Execution modeling** simulates fills and costs for backtests. [Design](docs/reference/lean_like_features.md) · [Example](qmtl/examples/strategies/execution_model_strategy.py)
- **Order publishing** turns signals into standardized orders for external services. [Docs](docs/guides/sdk_tutorial.md) · [Example](qmtl/examples/strategy.py)

## Development Workflow

Here’s a short workflow summary based on the repository’s guidelines:

1. **Environment Setup** – Use the `uv` tool and install dependencies in editable mode:

   ```bash
   uv pip install -e .[dev]
   ```

   This command ensures all development dependencies are available.

2. **Testing** – Run the tests in parallel via `uv` before committing:

   ```bash
   uv run -m pytest -n auto
   ```

   Commit only after tests pass.

3. **Design Approach** – Follow the Single Responsibility Principle (SRP) when designing modules and classes. This keeps features modular and easier to maintain.

For additional rules—such as adhering to architecture documents or managing distributable wheels—refer to [AGENTS.md](AGENTS.md) in the project root for the full guidelines.

## Documentation Dashboard

Document progress is tracked in [`docs/dashboard.json`](docs/dashboard.json). Each entry records the document's status (`draft`, `review`, or `complete`) and the responsible owner. The file's `last_updated` and `generated` timestamps are refreshed automatically by a scheduled workflow (`.github/workflows/docs-dashboard.yml`). Run the update script manually if needed:

```bash
python scripts/update_dashboard.py
```

Open the JSON directly or import it into a spreadsheet to review documentation status.

## Coding Style

Use consistent naming for connection strings across the project. Prefer the `*_dsn` suffix for all connection parameters (for example `redis_dsn`, `database_dsn`, `neo4j_dsn`, `kafka_dsn`). Avoid one-letter variable names except in short loops; use descriptive names like `redis_client` or `dagmanager`.

## Optional Modules

Install additional functionality on demand:

- [Indicators](qmtl/runtime/indicators/README.md)
- [IO](qmtl/io) &mdash; `pip install qmtl[io]`
- [Generators](qmtl/runtime/generators/README.md)
- [Transforms](qmtl/runtime/transforms/README.md)

## End-to-End Testing

Bring up the stack with Docker Compose:

```bash
docker compose -f tests/docker-compose.e2e.yml up -d
```

Run the tests in parallel using uv:

```bash
uv run -m pytest -n auto tests/e2e
```

See [docs/operations/e2e_testing.md](docs/operations/e2e_testing.md) for the full guide. For Docker stacks and commands, see [docs/operations/docker.md](docs/operations/docker.md).

## Running the Test Suite

Run all unit and integration tests in parallel with:

```bash
uv run -m pytest -n auto
```

## Monitoring

Load the sample alert definitions from `alert_rules.yml` into Prometheus to enable basic monitoring. Start the DAG Manager metrics server with `qmtl service dagmanager metrics` (pass `--port` to change the default 8000). For a full list of available alerts and Grafana dashboards, see [docs/operations/monitoring.md](docs/operations/monitoring.md).

## Running Services

Start the Gateway and DAG Manager using the combined configuration file or rely
on the built-in defaults. The ``--config`` flag is optional; without it both
services start in a local mode that uses SQLite and in-memory repositories. The
sample ``qmtl.yml`` file
demonstrates how to switch to Postgres, Neo4j and Kafka for production.

```bash
# start the gateway HTTP server with defaults
qmtl service gateway

# start the DAG Manager with defaults
qmtl service dagmanager server

# use a custom configuration file
qmtl service gateway --config qmtl/examples/qmtl.yml
qmtl service dagmanager server --config qmtl/examples/qmtl.yml

# submit a DAG diff
qmtl service dagmanager diff --file dag.json --target localhost:50051
```

Customize the sample YAML files in `qmtl/examples/` to match your environment.

See [gateway.md](docs/architecture/gateway.md) and [dag-manager.md](docs/architecture/dag-manager.md) for more
information on configuration and advanced usage.

### WorldService

WorldService owns world policies, decisions and activation state. Run it as a
stand‑alone FastAPI app and enable the Gateway proxy when needed.

1) Start WorldService (SQLite + Redis example)

```bash
cat > qmtl.yml <<'EOF'
worldservice:
  dsn: sqlite:///worlds.db
  redis: redis://localhost:6379/0
  bind:
    host: 0.0.0.0
    port: 8080
  auth:
    header: Authorization
    tokens: []
EOF
# Validate the file once before launching the service.
uv run qmtl config validate --config qmtl.yml --target schema --offline
uv run uvicorn qmtl.services.worldservice.api:create_app --factory --host 0.0.0.0 --port 8080
```

2) Point Gateway at WorldService (optional proxy)

- In `qmtl/examples/qmtl.yml`, set:
  - `gateway.worldservice_url: http://localhost:8080`
  - `gateway.enable_worldservice_proxy: true`

Then run Gateway with that config:

```bash
qmtl service gateway --config qmtl/examples/qmtl.yml
```

With the proxy enabled, SDKs can fetch decisions and activation via the
Gateway. When the proxy is disabled, SDKs operate in offline/backtest modes
without world decisions.

## SDK Tutorial

For instructions on implementing strategies with the SDK, see
[docs/guides/sdk_tutorial.md](docs/guides/sdk_tutorial.md).

## Example Strategies

Run the samples inside the `qmtl/examples/` directory:

```bash
python -m qmtl.examples.general_strategy
python -m qmtl.examples.strategies.indicators_strategy
python -m qmtl.examples.transforms_strategy
python -m qmtl.examples.generators_example
python -m qmtl.examples.extensions_combined_strategy
```

Ray is used automatically when installed. Append `--no-ray` to disable Ray-based execution:

```bash
python -m qmtl.examples.general_strategy --no-ray
```

See [qmtl/examples/README.md](qmtl/examples/README.md) for additional scripts such as `tag_query_strategy.py` or `ws_metrics_example.py`.

## TagQuery Node Resolution

`TagQueryNode` instances no longer resolve queues themselves. The
`TagQueryManager.resolve_tags()` method retrieves queue mappings from the Gateway
and updates all registered nodes. `Runner` creates a manager automatically and
invokes this method in every mode, so manual calls are rarely needed.

Resolved mappings are cached to `.qmtl_tagmap.json` (override with
`QMTL_TAGQUERY_CACHE`) along with a CRC so dry-runs and backtests can
reproduce the live mapping deterministically. `resolve_tags(offline=True)`
hydrates nodes from this snapshot when the Gateway is unavailable.

`ProcessingNode` instances accept either a single upstream `Node` or a list of nodes via the `input` parameter. Dictionary inputs are no longer supported.

See [docs/reference/faq.md](docs/reference/faq.md) for common questions such as using `TagQueryNode` during backtesting.

Dry‑run parity: the `POST /strategies/dry-run` endpoint mirrors the queue mapping of the real submission path and always returns a non‑empty `sentinel_id`. When the Diff path is unavailable, the server derives a deterministic fallback of the form `dryrun:<crc32>` over DAG node IDs.

## Backfills

[docs/operations/backfill.md](docs/operations/backfill.md) explains how to preload historical data by
injecting `HistoryProvider` instances
into `StreamInput` nodes. These dependencies must be provided at creation time
and cannot be reassigned later. The same guide covers persisting data via
`EventRecorder`.

Example injection:

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
        dsn="postgresql://user:pass@localhost:8812/qdb"
    ),
    event_service=EventRecorderService(
        QuestDBRecorder(dsn="postgresql://user:pass@localhost:8812/qdb")
    ),
)
```

``QuestDBHistoryProvider`` (also exported as ``QuestDBLoader`` for backwards
compatibility) and ``QuestDBRecorder`` will default to using
``stream.node_id`` as the table name if ``table`` is not provided.

[docs/operations/backfill.md](docs/operations/backfill.md).

### QuestDBHistoryProvider with a custom fetcher

`QuestDBHistoryProvider` can pull missing rows from any async source. Implement a
`DataFetcher` and pass it to the loader:

```python
import httpx
import pandas as pd
from qmtl.runtime.sdk import DataFetcher, QuestDBHistoryProvider

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
loader = QuestDBHistoryProvider(
    dsn="postgresql://user:pass@localhost:8812/qdb",
    fetcher=fetcher,
)
```
