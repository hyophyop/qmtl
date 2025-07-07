# Strategy Development and Testing Workflow

This guide walks through the typical steps for creating and validating a new QMTL
strategy. It starts from project initialization using `qmtl init` and concludes
with running the test suite.

## 1. Initialize a Project

Create a dedicated directory for your strategy and generate the scaffold:

```bash
qmtl init --path my_qmtl_project
cd my_qmtl_project
```

The command copies a sample `strategy.py`, a `qmtl.yml` configuration and empty
packages for `generators`, `indicators` and `transforms`. These packages let you
extend the SDK by adding custom nodes.

Install optional extras so Python can discover these extensions:

```bash
uv pip install -e .[generators,indicators,transforms]
```

## 2. Explore the Scaffold

- `strategy.py` – a minimal example strategy using the SDK.
- `qmtl.yml` – sample configuration for the Gateway and DAG manager.
- `generators/`, `indicators/`, `transforms/` – extension packages where you can
  implement additional nodes.

Run the default strategy to verify that everything works:

```bash
python strategy.py
```

This uses `Runner.offline()` behind the scenes to execute without external
services.

## 3. Develop Your Strategy

Edit `strategy.py` or create new modules inside the extension packages. Each
strategy subclasses `Strategy` and defines a `setup()` method that wires up
`Node` instances. Useful base classes include `StreamInput`, `TagQueryNode` and
`ProcessingNode`. See [docs/sdk_tutorial.md](sdk_tutorial.md) for a full
introduction to these concepts.

Configuration options such as connection strings live in `qmtl.yml`. The file is
ready for local development but can be adjusted to point at production services.

## 4. Execute in Different Modes

Run strategies via the CLI or programmatically with `Runner`.

```bash
python -m qmtl.sdk mypkg.strategy:MyStrategy --mode backtest \
    --start-time 2024-01-01 --end-time 2024-02-01 \
    --gateway-url http://localhost:8000
```

Available modes are `backtest`, `dryrun`, `live` and `offline`. The first three
require a running Gateway and DAG manager. Multiple strategies can be executed
in parallel by launching separate processes or using the
`parallel_strategies_example.py` script.

## 5. Test Your Implementation

Always run the unit tests before committing code:

```bash
uv run -m pytest -W error
```

End‑to‑end tests require Docker. Start the stack and execute the tests:

```bash
docker compose -f tests/docker-compose.e2e.yml up -d
uv run -- pytest tests/e2e
```

For details on the test environment refer to
[docs/e2e_testing.md](e2e_testing.md). Building wheels can run concurrently with
tests if desired:

```bash
# Example of running wheels and tests in parallel
uv pip wheel . &
uv run -m pytest -W error
wait
```

## 6. Next Steps

Consult [architecture.md](../architecture.md) for a deep dive into the overall
framework and `examples/` for reference strategies. When ready, deploy the
Gateway and DAG manager using your customized `qmtl.yml`.
