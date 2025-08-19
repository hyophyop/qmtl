# Strategy DAG Guide

This guide explains how to define node processors, combine them into DAGs, and reuse components across strategies.

## Node Processor Definition

Node processors are pure functions located under the `nodes/` package. Name each function with the `_node` suffix so it can be easily identified and reused.

```python
# nodes/generators/price.py

def price_generator_node():
    """Generate the latest price as a dictionary."""
    return {"price": 100}
```

## Composing a DAG

Use `qmtl.dag_manager` to wire processors into an acyclic graph. Inputs are mapped by explicit keys, allowing outputs from one node to feed downstream nodes.

```python
from qmtl.dag_manager import DAGManager
from nodes.generators.price import price_generator_node
from nodes.indicators.moving_average import moving_average_node
from nodes.transforms.signal import signal_transform_node

dag = DAGManager()
dag.add_node("price", price_generator_node)
dag.add_node("ma", moving_average_node, inputs={"data": "price"})
dag.add_node("signal", signal_transform_node, inputs={"metric": "ma"})

result = dag.execute()
```

### Dependency Diagram

```mermaid
graph TD
    price_generator_node --> moving_average_node --> signal_transform_node
```

## Reusing Nodes

Because processors are pure functions, a single node can serve multiple DAGs. For example, `price_generator_node` may feed both a mean-reversion and a momentum strategy without modification.

```python
# dags/mean_reversion_dag.py
from nodes.generators.price import price_generator_node
from nodes.indicators.moving_average import moving_average_node

def build_dag():
    ...
```

This reuse minimizes duplication and keeps strategies consistent.

## Configuration

`config.example.yml` contains optional settings that influence node behavior. The
`load_config` helper parses these sections and supplies them when building
strategy nodes:

- `performance_metrics`: currently supports `risk_free_rate` for
  `alpha_performance_node`.
- `signal_thresholds`: `long` and `short` thresholds used by
  `TradeSignalGeneratorNode`.
- `risk_limits`: trade sizing and protections (`size`, `stop_loss`,
  `take_profit`) forwarded to `TradeSignalGeneratorNode`.
- `questdb_dsn`: connection string for `QuestDBRecorder` and `QuestDBLoader`.
- `gateway_url`: URL for posting DAGs when running live or dry-run sessions.
- `dags`: mapping of strategy names to booleans for enabling each DAG.
- `streams`: list of `{symbol, interval}` pairs to backfill in parallel.

Example YAML with a custom QuestDB DSN and multiple symbols:

```yaml
questdb_dsn: "postgresql://user:pass@questdb:8812/qdb"
gateway_url: "http://localhost:8080"
streams:
  - symbol: BTCUSDT
    interval: "60s"
  - symbol: ETHUSDT
    interval: "5m"
backtest:
  start_time: "2024-01-01T00:00:00Z"
  end_time: "2024-02-01T00:00:00Z"
```

## Alpha Signal Strategy

`dags/alpha_signal_dag.py` chains a data stream, alpha calculation,
`alpha_history_node`, `AlphaPerformanceNode`, `TradeSignalGeneratorNode`
and `TradeOrderPublisherNode` into a full alpha-to-order pipeline.

Enable it via the `dags` section in `config.example.yml`:

```yaml
dags:
  alpha_signal: true
```

`strategy.py` reads these toggles so multiple DAGs can run concurrently.

## Binance History Strategy

The `dags/binance_history_dag.py` module demonstrates wiring a `StreamInput`
with `QuestDBLoader` and `QuestDBRecorder` so Binance kline data is
persisted to QuestDB and missing ranges can be backfilled via
`BinanceFetcher`.

### Initialization

Before executing `BinanceHistoryStrategy`, create the QuestDB table using the
SQL script in `binance_history_strategy/`:

```bash
psql < strategies/binance_history_strategy/create_table.sql
```

The script defines `node_id VARCHAR`, `interval INT`, `ts TIMESTAMP`, and
price/volume columns (`open`, `high`, `low`, `close`, `volume`). Running it
ensures the recorder can persist data when the strategy starts.

### Metrics and Monitoring

Start the QMTL metrics server so Prometheus can scrape backfill progress and
other runtime statistics:

```python
from qmtl.sdk import metrics

metrics.start_metrics_server(port=8000)
```

Add the endpoint to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "qmtl"
    static_configs:
      - targets: ["localhost:8000"]
```

Configure Grafana with this Prometheus data source and create panels using
metrics such as `backfill_jobs_in_progress` or
`backfill_last_timestamp` to visualize backfill activity.
