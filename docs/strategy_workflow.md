# Strategy Development and Testing Workflow

This guide walks through the typical steps for creating and validating a new QMTL
strategy. It starts with installing the SDK and project initialization and
concludes with running the test suite.

## 0. Install QMTL

Create a virtual environment and install the package in editable mode. The
[README](../README.md) describes the details, but the basic steps are:

```bash
uv venv
uv pip install -e .[dev]
```

Optional extras such as `generators`, `indicators` or `transforms` are installed
from the repository root (or from PyPI) **before** creating your project
directory:

```bash
uv pip install -e .[generators,indicators,transforms]
```

## 1. Initialize a Project

Create a dedicated directory for your strategy and generate the scaffold:

```bash
qmtl init --path my_qmtl_project
cd my_qmtl_project
```

The command copies a sample `strategy.py`, a `qmtl.yml` configuration and empty
packages for `generators`, `indicators` and `transforms`. These folders let you
extend the SDK by adding custom nodes. Because the extras were installed in the
previous step, no additional `pip install` commands are required inside the
project directory.

## 2. Explore the Scaffold

- `strategy.py` – a minimal example strategy using the SDK.
- `qmtl.yml` – sample configuration for the Gateway and DAG manager.
- `generators/`, `indicators/`, `transforms/` – extension packages where you can
  implement additional nodes.

Run the default strategy to verify that everything works:

```bash
python strategy.py
```
The scaffolded script invokes `Runner.backtest()` which expects a running
Gateway and DAG manager. Provide a `--gateway-url` argument, or modify the
script to use `Runner.offline()` when testing without external services.

## 2a. Example Run Output

The following snippet demonstrates the results of executing the above commands in a clean
container. After creating the scaffold the directory structure looks like:

```text
$ ls -R my_qmtl_project | head
my_qmtl_project:
generators
indicators
qmtl.yml
strategy.py
transforms
...
```

Attempting to install the optional extras directly fails because the scaffold does not contain
`pyproject.toml`:

```text
$ uv pip install -e .[generators,indicators,transforms]
error: /tmp/my_qmtl_project does not appear to be a Python project, as neither `pyproject.toml` nor `setup.py` are present in the directory
```

Run the command from the repository root instead (or install from PyPI) to make
the extras available.

Running the default strategy without a Gateway URL also produces an error:

```text
$ python strategy.py
RuntimeError: gateway_url is required for backtest mode
```

Provide a `--gateway-url` argument or modify the script to use `Runner.offline()` when running locally.

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
require a running Gateway and DAG manager. Start them in separate terminals:

```bash
qmtl gw --config examples/qmtl.yml
qmtl dagmgr-server --config examples/qmtl.yml
```

Multiple strategies can be executed in parallel by launching separate processes
or using the `parallel_strategies_example.py` script.

## 5. Test Your Implementation

Always run the unit tests before committing code:

```bash
uv run -m pytest -W error
```

A sample execution inside the container finished successfully:

```text
======================= 260 passed, 1 skipped in 47.15s ========================
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
