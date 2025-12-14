# Strategy submission & gating flow

This guide stitches together offline validation, world-driven runs, activation gates, and metrics so strategy authors can move from local smoke tests to WorldService evaluation smoothly. Detailed policy mechanics live in [world/world.md](../world/world.md).

## 1) Prereqs

- A `Strategy` subclass (e.g., `strategies.beta_factory.demo.StrategyCls`)
- Gateway URL + world ID
- History/backfill path: use the default `SeamlessDataProvider` when possible ([history_data_quickstart.md](./history_data_quickstart.md))

## 2) Local validation (offline)

```python
from qmtl.runtime.sdk import Runner
from strategies.beta_factory.demo import StrategyCls

Runner.submit(
    StrategyCls,
    history_start=1700000000,
    history_end=1700003600,
    # Optional: attach seamless data directly to streams missing a provider
    # data=my_seamless_provider,
)
```

- Validates DAG/node schemas and history warmup without hitting Gateway.
- If you pass `data=`, seamless providers are auto-attached to streams that lack a `history_provider`.

## 3) Submit to a world (run)

### CLI (preferred)

```bash
qmtl submit strategy.py --world my-world
```

### Python API

```python
Runner.submit(
    StrategyCls,
    world="my-world",
)
```

- Runner fetches `effective_mode` (validate/backtest/paper/live, etc.) from WorldService and applies gates accordingly.
- Provide `history_start` / `history_end` when you want an explicit window; otherwise the default world/provider coverage is used.

## 4) Apply activation gates

- **ActivationManager**: WorldService maintains the activation table; the SDK consumes it to allow/deny orders.
  - Gateway API: `GET /worlds/{world_id}/activation` (weights/active flags)
  - WS broadcast: subscribe to activation changes if available
- Place a gate node in front of order submission, or rely on `ExecutionDomain` (`validate/backtest`) to auto-block orders.

## 5) Metrics feedback loop

- `Runner._postprocess_result` exports alpha performance metrics into SDK metrics; enable Prometheus scraping so WorldService can evaluate policies immediately.
- Strategies may emit extra metrics (node outputs or custom metrics). Keep naming aligned with your policy DSL (gates/score/constraints).

## 6) Safety checks

- Keep `schema_enforcement="fail"` to guard node schema consistency.
- For live runs, require `--allow-live` / world-scoped RBAC, and confirm orders are blocked when `effective_mode` is `validate`.
- If data currency/coverage is insufficient, WorldService may downgrade to `validate`; check logs for `effective_mode` + reason.

## 7) Further reading

- World policies and gates: [world/world.md](../world/world.md)
- History data attachment: [history_data_quickstart.md](./history_data_quickstart.md)
- DAG/node authoring tutorial: [sdk_tutorial.md](./sdk_tutorial.md)
