---
title: "Strategy Development and Testing Workflow"
tags: []
author: "QMTL Team"
last_modified: 2025-11-05
---

{{ nav_links() }}

# Strategy Development and Testing Workflow

> **Practical development guide and checklist**
>
> - **Separation of concerns (SoC)**: keep modules single‑responsibility; depend on interfaces. See [architecture.md](../architecture/architecture.md).
> - **Test independence**: avoid inter‑test coupling; use clear assertions and messages.
> - **Coding rules**: modularize code, split functions, and document with comments/docstrings.
> - **Troubleshooting**: for install/run/connectivity issues, see [FAQ](../reference/faq.md) and the "Common issues" section below.
> - **Operations/deploy**: before deployment, verify tests, backup configs, define rollback, and configure monitoring. See [monitoring](../operations/monitoring.md) and [canary rollout](../operations/canary_rollout.md).
> - **Folder/file quick reference**:
>   - `strategy.py`: entry point; Strategy implementation
>   - `qmtl.yml`: environment/services config
>   - `generators/`, `indicators/`, `transforms/`: custom node implementations
>   - `tests/`: unit and integration tests

---

This guide walks through the typical steps for creating and validating a new QMTL
strategy. It starts with installing the SDK and project initialization and
concludes with running the test suite.

## 0. Install QMTL

Create a virtual environment and install the package in editable mode. The
[docs home](../index.md) describes the details, but the basic steps are:

```bash
uv venv
uv pip install -e .[dev]
```

## 1. Initialize a Project

Create a dedicated directory for your strategy and generate the scaffold. List
available presets, then initialize the project with a chosen preset and optional
sample data:

```bash
qmtl project list-presets
qmtl project init --path my_qmtl_project --preset minimal --with-sample-data
cd my_qmtl_project
```

The command copies a sample `strategy.py`, a `qmtl.yml` configuration and empty
packages for `generators`, `indicators` and `transforms`. These folders let you
extend the SDK by adding custom nodes.


## 2. Explore the Scaffold

- `strategy.py` – a minimal example strategy using the SDK.
- `qmtl.yml` – sample configuration for the Gateway and DAG Manager.
- `generators/`, `indicators/`, `transforms/` – extension packages where you can
  implement additional nodes.

> **Structure note:** See the above checklist for folder/file roles.

Run the default strategy to verify that everything works. Offline mode is used
when no external services are configured:

```bash
python strategy.py
```
The scaffolded script uses `Runner.submit()` by default, so no external
services are required. To connect to your environment, update the script to call
`Runner.submit(world=...)`, which follows WorldService decisions
and activation events.

The Gateway proxies the WorldService, and SDKs receive control events over the tokenized WebSocket returned by `/events/subscribe`. Activation and queue updates arrive through this opaque control stream instead of being read directly from Gateway state.

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

If the script calls `Runner.submit(...)` without a reachable Gateway/WorldService,
the strategy will remain in a safe compute‑only state (order gates OFF) until
the control connection is restored.

> **Common issues**
> - Missing Gateway URL: add `--gateway-url` or use `Runner.submit()`
> - Dependency conflicts: reinstall via `uv pip install -e .[dev]`

## 3. Develop Your Strategy

Edit `strategy.py` or create new modules inside the extension packages. Each
strategy subclasses `Strategy` and defines a `setup()` method that wires up
`Node` instances. Useful base classes include `StreamInput`, `TagQueryNode` and
`ProcessingNode`. See [docs/sdk_tutorial.md](sdk_tutorial.md) for a full
introduction to these concepts.

Configuration options such as connection strings live in `qmtl.yml`. The file is
ready for local development but can be adjusted to point at production services.

> **Development guidelines**
> - Keep each node single‑responsibility and interact via interfaces.
> - Split complex logic into functions/classes and document with docstrings.
> - Update relevant docs and tests alongside code changes.

## 3a. Intent-first pipeline

Rebalancing policies stay most flexible when strategies emit **intents only**. A
`PositionTargetNode` converts a signal into target allocations and
`nodesets.recipes.make_intent_first_nodeset` wraps it in the standard execution
pipeline (pre-trade → sizing → execution → publish). A minimal setup looks like:

```python
from qmtl.runtime.nodesets.recipes import (
    INTENT_FIRST_DEFAULT_THRESHOLDS,
    make_intent_first_nodeset,
)
from qmtl.runtime.sdk import Strategy
from qmtl.runtime.sdk.node import StreamInput


class IntentFirstStrategy(Strategy):
    def setup(self) -> None:
        signal = StreamInput(tags=["alpha"], interval=60, period=1)
        price = StreamInput(tags=["price"], interval=60, period=1)

        nodeset = make_intent_first_nodeset(
            signal,
            self.world_id,
            symbol="BTCUSDT",
            price_node=price,
            thresholds=INTENT_FIRST_DEFAULT_THRESHOLDS,
            long_weight=0.25,
            short_weight=-0.10,
        )

        self.add_nodes([signal, price])
        self.add_nodeset(nodeset)
```

Tune optional parameters such as `thresholds`, `initial_cash`, or
`execution_model` to match your hysteresis bands and sizing seeds. If you need a
recipe adapter, expose it via `IntentFirstAdapter` so the DAG Manager can bind
signal/price inputs externally. See [reference/intent.md](../reference/intent.md)
for parameter details.

## 4. Execute with Worlds

Use `Runner.submit()` for local testing without dependencies. For integrated runs,
switch to `Runner.submit(strategy_cls, world=...)`. Activation and queue
updates are delivered via the Gateway's opaque control stream on the `/events/subscribe`
WebSocket; WS remains the authority for policy and activation.

Execution mode/domain rules (WS-first, default-safe):

- Only `mode=backtest|paper|live` are accepted; `execution_domain` hints are ignored.
- WS `effective_mode` is authoritative; missing/ambiguous modes are forced to compute-only (backtest).
- In `backtest`/`paper`, missing `as_of` or `dataset_fingerprint` triggers safe-mode downgrades (`downgrade_reason=missing_as_of`, orders gated).
- `ActivationEnvelope`/`DecisionEnvelope` carry `compute_context` and serialize identically across WS/Runner/CLI; CLI `--output json` shows the same structure.

```bash
# start with built-in defaults
qmtl service gateway
qmtl service dagmanager server

# or load a custom configuration
qmtl service gateway --config qmtl/examples/qmtl.yml
qmtl service dagmanager server --config qmtl/examples/qmtl.yml
```

Multiple strategies can be executed in parallel by launching separate processes
or using the `parallel_strategies_example.py` script.

> **Tip:** In production, back up `qmtl.yml` and prepare a rollback plan.

## 4a. Intent → Rebalancing → Execution end-to-end

Intent-first strategies shine when coupled with the world/gateway rebalancing
stack. The end-to-end flow follows three stages:

1. **Strategy:** The `PositionTargetNode` pipeline above emits intents with
   `target_percent`/`quantity` payloads.
2. **World Service:** The centralized rebalancer in
   [world/rebalancing.md](../world/rebalancing.md) aggregates intents whenever
   world/strategy allocations shift and computes delta positions.
3. **Gateway execution:** The adapter described in
   [operations/rebalancing_execution.md](../operations/rebalancing_execution.md)
   turns the deltas into orders via `orders_from_world_plan` or the
   `/rebalancing/execute` endpoint and, if required, submits them to the Commit
   Log.

For local validation, run the strategy with `Runner.submit()` while posting
`MultiWorldRebalanceRequest` payloads to the World Service to inspect plans, then
review the Gateway dry-run response to confirm order shapes. Providing activation
and Gateway URLs enables the exact same flow in integrated environments.

When the WorldService `compat_rebalance_v2` toggle is enabled, include
`schema_version=2` in your local requests and be prepared to consume the
resulting `alpha_metrics` envelope (`AlphaMetricsEnvelope` contains `per_world`
and `per_strategy` `alpha_performance` stats). The `alpha_metrics_required`
setting rejects `schema_version<2` submissions, so the `docs/operations/rebalancing_schema_coordination.md`
checklist should be satisfied before flipping the flag to keep Gateway/SDK
consumers in lockstep.【F:qmtl/services/worldservice/routers/rebalancing.py#L54-L187】【F:qmtl/services/worldservice/schemas.py#L245-L308】

## 5. Test Your Implementation

Always run the unit tests in parallel before committing code:

```bash
uv run -m pytest -W error -n auto
```

A sample execution inside the container finished successfully:

```text
======================= 260 passed, 1 skipped in 47.15s ========================
```

End‑to‑end tests require Docker. Start the stack and execute the tests:

```bash
docker compose -f tests/docker-compose.e2e.yml up -d
uv run -m pytest -n auto tests/e2e
```

For details on the test environment refer to
[docs/operations/e2e_testing.md](../operations/e2e_testing.md). Building wheels can run concurrently with
tests if desired:

```bash
# Example of running wheels and tests in parallel
uv pip wheel . &
uv run -m pytest -W error -n auto
wait

### Test Teardown and Shutdown

When a test starts background services (e.g., TagQueryManager subscriptions or ActivationManager), prefer explicit cleanup:

```python
strategy = Runner.submit(MyStrategy, world="w", mode="paper")
try:
    ...  # assertions
finally:
    Runner.shutdown(strategy)
```

`Runner.shutdown` is idempotent and safe to call even if no background services are active.

### Test Mode Budgets

Enable `test.test_mode` in `qmtl.yml` to apply conservative client-side time budgets that reduce the chance of hangs in flaky environments:

- HTTP clients: short polling intervals and explicit health checks
- WebSocket client: shorter receive timeout and overall max runtime (≈5s)

```yaml
test:
  test_mode: true
```
```

> **Test authoring tips**
> - Keep tests independent; avoid cross‑test dependencies.
> - Use clear assertion messages to diagnose failures quickly.
> - Define coverage targets and test critical logic.
> - Separate unit and integration tests.

## 6. Next Steps

Consult [architecture.md](../architecture/architecture.md) for a deep dive into the overall
framework and `qmtl/examples/` for reference strategies. When ready, deploy the
Gateway and DAG Manager using your customized `qmtl.yml`.

> **Ops/deploy checklist**
> - Tests pass and coverage meets targets
> - Config files backed up and versioned
> - Monitoring/alerts configured ([monitoring](../operations/monitoring.md))
> - Progressive rollout/rollback plan ([canary rollout](../operations/canary_rollout.md))
> - Post‑deploy log/metric checks

> **References**
> - [architecture.md](../architecture/architecture.md): system overview
> - [sdk_tutorial.md](sdk_tutorial.md): SDK and strategy examples
> - [faq.md](../reference/faq.md): frequently asked questions
> - [monitoring.md](../operations/monitoring.md): monitoring and operations
> - [canary_rollout.md](../operations/canary_rollout.md): progressive rollout
> - [qmtl/examples/]({{ code_url('qmtl/examples/') }}): example strategies

{{ nav_links() }}
