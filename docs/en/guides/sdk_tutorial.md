---
title: "SDK Usage Guide"
tags: []
author: "QMTL Team"
last_modified: 2025-12-05
---

{{ nav_links() }}

# SDK Usage Guide

Core Loop paved road only: world-driven `Runner.submit`, WS envelopes as SSOT, and world data presets. Backtest-only without a world is a secondary path.

## 0. Install and start a project

```bash
uv venv
uv pip install -e .[dev]
qmtl project init --path my_qmtl_project --preset minimal --with-sample-data
cd my_qmtl_project
```

## 1. Strategy skeleton

Register nodes in `Strategy.setup()`. Minimal Core Loop example:

```python
from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import StreamInput, ProcessingNode


class MyStrategy(Strategy):
    def setup(self) -> None:
        price = StreamInput(tags=["price"], interval=60, period=60)

        def compute(view):
            return {"alpha": float(view.last("price"))}

        self.add_nodes([price, ProcessingNode(input=price, compute_fn=compute, name="alpha")])


if __name__ == "__main__":
    Runner.submit(MyStrategy, world="demo_world", mode="backtest", data_preset="ohlcv.binance.spot.1m")
```

- `StreamInput` and `ProcessingNode` cover the simplest source/compute path.
- Add `TagQueryNode` for tag-based multi-queue input; let Gateway/WS own queue resolution and policies.

## 2. Submission surface and mode rules

- `Runner.submit(..., world=..., mode=backtest|paper|live, data_preset=...)`
- CLI mirrors it: `qmtl submit strategies.my:MyStrategy --world ... --mode ... --data-preset ...`
- Exposed modes are `backtest|paper|live` only; legacy tokens (`offline`/`sandbox`) normalize to `backtest`.
- WS `effective_mode` is authoritative; ambiguous/missing/stale inputs downgrade to compute-only (backtest).
- In `backtest/paper`, missing `as_of` or `dataset_fingerprint` surfaces `downgraded/safe_mode` at the top level.

| Surface | Rule |
| --- | --- |
| `--mode` | Only `backtest|paper|live`; omission forces compute-only (backtest). |
| execution_domain hints | Internally mapped to canonical modes; hidden from the user surface. |
| WS envelope | `DecisionEnvelope`/`ActivationEnvelope` serialized verbatim. |
| `precheck` | Local ValidationPipeline only; non-authoritative. |

## 3. SubmitResult (WS SSOT vs precheck)

`--output json` (abridged):

```json
{
  "strategy_id": "demo_strategy",
  "world": "demo_world",
  "mode": "backtest",
  "downgraded": true,
  "downgrade_reason": "missing_as_of",
  "ws": { "decision": { "...": "..." }, "activation": { "...": "..." } },
  "precheck": { "status": "validating", "violations": [] }
}
```

- Only `ws.*` is the SSOT (mirrors the CLI `🌐 WorldService decision (SSOT)` section).
- `precheck` is advisory; contract tests (`tests/e2e/core_loop`) assert WS/precheck separation.
- `downgraded/safe_mode` expose default-safe downgrades immediately.

## 4. Data preset auto-wiring

- Pick from `world.data.presets[]`; Runner/CLI auto-wire Seamless into each `StreamInput.history_provider`.
- Invalid preset IDs fail fast; omission uses the first preset.
- Rules/examples: [world/world.md](../world/world.md), [architecture/seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md).

```bash
uv run qmtl submit strategies.my:MyStrategy \
  --world demo_world \
  --data-preset ohlcv.binance.spot.1m \
  --mode backtest
```

## 5. Intent/order pipeline (brief)

- Intent-first recipe: `nodesets.recipes.make_intent_first_nodeset`, see [reference/intent.md](../reference/intent.md).
- Order delivery: `TradeOrderPublisherNode` + `Runner.set_trade_order_*` hooks (HTTP/Kafka/custom). If unset, orders are ignored so strategies stay backend-agnostic.
- Rebalancing tie-in: [world/rebalancing.md](../world/rebalancing.md), [operations/rebalancing_execution.md](../operations/rebalancing_execution.md).

## 6. Cache and test tips

- `compute_fn` receives a read-only `CacheView`; `NodeCache.snapshot()` is internal.
- PyArrow cache/eviction cadence and test-mode time budgets: see [operations/e2e_testing.md](../operations/e2e_testing.md) and `cache.*` settings.
- Run contract/unit tests in parallel: `uv run -m pytest -W error -n auto`.

## Appendix — TagQuery/WebSocket, timing, fills

- TagQueryManager/WebSocket token exchange and sentinel weight events: see the appendix in [strategy_workflow.md](strategy_workflow.md) and inline source comments.
- Cost/timing simulation with `ExecutionModel`/`TimingController`: [operations/timing_controls.md](../operations/timing_controls.md) and the example `qmtl/examples/strategies/order_pipeline_strategy.py`.
- Backfill/data prep: [operations/backfill.md](../operations/backfill.md).

{{ nav_links() }}
