---
title: "Strategy Development and Testing Workflow"
tags: []
author: "QMTL Team"
last_modified: 2025-12-06
---

{{ nav_links() }}

# Strategy Development and Testing Workflow

This guide follows the Core Loop paved road: **Runner.submit + world/preset**. “Backtest-only without a world” is treated as an appendix; the main path keeps the surface aligned with WS decision/activation (SSOT).

## 0. Setup — install and create a project

```bash
uv venv
uv pip install -e .[dev]
qmtl project init --path my_qmtl_project --preset minimal --with-sample-data
cd my_qmtl_project
```

- `strategy.py` ships with a Core Loop example; `qmtl.yml` carries default world/gateway settings.
- Extend the SDK via `generators/`, `indicators/`, `transforms/` as needed.

## 1. Minimal Core Loop strategy

A world-backed strategy that runs with only `Runner.submit`. Using a world preset auto-injects the `history_provider` for each `StreamInput`.

```python
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import StreamInput, ProcessingNode


class DemoStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(tags=["price"], interval=60, period=60)

        def compute(view):
            return {"alpha": float(view.last("price"))}

        alpha = ProcessingNode(input=price, compute_fn=compute, name="alpha")
        self.add_nodes([price, alpha])


if __name__ == "__main__":
    Runner.submit(DemoStrategy, world="demo_world", mode="backtest", data_preset="ohlcv.binance.spot.1m")
```

## 2. Submit and read results (WS SSOT)

```bash
uv run qmtl submit strategies.demo:DemoStrategy \
  --world demo_world \
  --mode backtest \
  --data-preset ohlcv.binance.spot.1m \
  --output json
```

- **WS envelope = SSOT**: `ws.decision`/`ws.activation` reuse the WorldService schema; the CLI `🌐 WorldService decision (SSOT)` section prints the same fields.
- **Precheck is separate**: local ValidationPipeline output lives only under `precheck`.
- **Default-safe**: ambiguous modes or missing `as_of` downgrade to compute-only (backtest) and surface `downgraded/safe_mode` at the top level.
- The contract suite (`tests/e2e/core_loop`) pins these schemas and downgrade rules.

## 3. Data preset on-ramp

- Pick one of `world.data.presets[]` and Runner/CLI auto-wires Seamless into each `StreamInput.history_provider`.
- Missing preset IDs fail fast; omission falls back to the first preset.
- Rules and examples live in [world/world.md](../world/world.md) and [architecture/seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md).

## 4. Core Loop checklist

- Submission: use `Runner.submit(..., world=..., mode=backtest|paper|live)` only; legacy `offline/sandbox` normalize to `backtest`.
- Result surface: `SubmitResult.ws.*` must mirror WS envelopes; `precheck` is advisory only.
- Activation/deploy: WS owns authority; weights/TTL/etag come straight from WS, and ambiguous inputs downgrade to compute-only.
- Allocation: inspect/apply world allocations with `qmtl world allocations|rebalance-*`.

## 5. Templates and next steps

- Core Loop-aligned templates: [sdk_tutorial.md](sdk_tutorial.md), [world/world.md](../world/world.md), [world/policy_engine.md](../world/policy_engine.md)
- Intent-first/rebalancing pipeline: [reference/intent.md](../reference/intent.md), [operations/rebalancing_execution.md](../operations/rebalancing_execution.md)
- Operations/monitoring: [operations/monitoring.md](../operations/monitoring.md), [operations/activation.md](../operations/activation.md)

## Appendix — legacy/backtest-only path

- Local experiments without a world run via `Runner.submit(..., mode="backtest")`. This is a secondary path and does not bypass WS/activation/queue rules.
- TagQuery/WebSocket details, test-mode budgets, and backfill tips live in [sdk_tutorial.md](sdk_tutorial.md) and [operations/e2e_testing.md](../operations/e2e_testing.md).

{{ nav_links() }}
