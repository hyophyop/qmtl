---
title: "SR × Runner.submit Auto Returns Derivation Sketch"
tags: [design, sr, validation, returns]
author: "QMTL Team"
last_modified: 2025-11-29
status: draft
---

# SR × Runner.submit Auto Returns Derivation Sketch

## 0. As-Is / To-Be Summary

- As-Is
  - This memo sketches a lightweight way to pair SR templates with Runner.submit via an `auto_returns` option, but the current Runner/WS/Seamless paths do not implement auto_returns and SR strategies are not connected to Runner.submit + auto-validate unless they explicitly produce returns.
- To-Be
  - Once the unified design in `auto_returns_unified_design.md` lands, SR templates should flow naturally into the Core Loop (submit → evaluation → activation) via `auto_returns` settings.
  - This memo stays as a companion note from an SR perspective (data consistency, validation samples, expression_key dedup) and keeps the As-Is banner up top to clarify that this is an unimplemented draft.

> **Related issue**: [hyophyop/qmtl#1723](https://github.com/hyophyop/qmtl/issues/1723)
> **Related design docs**: [`auto_derive_returns_proposal.md`](../../ko/design/auto_derive_returns_proposal.md), [`sr_integration_proposal.md`](../../ko/design/sr_integration_proposal.md)

Canonical content lives in `docs/ko/...`; this English page mirrors the Korean draft so English builds succeed while translations are completed.

This memo summarizes how SR/feed-driven strategies could opt in to **auto-deriving a minimal returns series from price data inside Runner.submit** without directly wiring `returns`/`equity`/`pnl`.

## 1. Background

- Runner.submit/submit_async currently interprets returns in this order:
  1. Use the `returns` argument if provided.
  2. Look for `returns` → `equity` (pct_change) → `pnl` on the strategy via `_extract_returns_from_strategy`.
  3. If all are empty, reject with `"strategy produced no returns; auto-validation cannot proceed"` when `auto_validate=True`.
- Simple SR/feed strategies often only consume price streams, so **boilerplate wiring of returns is a hurdle despite having enough data**.
- `docs/ko/design/auto_derive_returns_proposal.md` covers SDK-wide opt-in auto-derive. This memo focuses on **how the SR path could feed into Runner.submit**.

## 2. Goals

- Keep default behavior unchanged and only derive returns for **explicit opt-in strategies**.
- ValidationPipeline/WorldService still expect “returns provided already”; auto-returns lives in the **Runner.submit pre-processing layer** only.
- SR/feed strategies should pass auto-validation with a small config, while production strategies continue to supply explicit `returns`/`equity`/`pnl` first.

## 3. Runner.submit API Sketch

Introduce an opt-in flag on Runner.submit/submit_async:

```python
async def submit_async(
    strategy_cls: type["Strategy"] | "Strategy",
    *,
    # ... existing params ...
    auto_returns: bool | "AutoReturnsConfig" | None = None,
) -> SubmitResult: ...
```

- `auto_returns=None` (default): current behavior; no auto-derive attempt.
- `auto_returns=True`: “simple default” (e.g., pct_change on the first price node `close`).
- `auto_returns=AutoReturnsConfig(...)`: explicitly control node/field/method.

Conceptual config object:

```python
@dataclass
class AutoReturnsConfig:
    node: str | None = None           # e.g., "price", "ccxt:BTCUSDT"
    field: str = "close"              # e.g., "close", "price", "mid"
    method: Literal["pct_change", "log_return"] = "pct_change"
    min_length: int | None = None     # reject if too short
```

In the SR path, ExpressionDagBuilder/Seamless Provider can publish **standard price node/field conventions** to feed into this config.

## 4. Priority and Failure Handling

Proposed precedence:

1. If the caller passes `returns`, use it and skip auto-derive.
2. Otherwise use the existing `_extract_returns_from_strategy` flow:
   - `strategy.returns` → `strategy.equity` → `strategy.pnl`.
3. If returns are still empty and `auto_returns` is truthy, try **auto-derive**.
4. If auto-derive fails or yields `min_length`-insufficient data, keep rejecting with `"no returns; auto-validation cannot proceed"` but add improvement hints such as `"auto_returns enabled but no usable price series found for node=..., field=..."`.

This keeps:

- **Explicit returns/equity/pnl always first**, and
- Auto-derive strictly as an opt-in fallback.

## 5. Derivation Helper Utility

Prefer a separate SDK utility over embedding price logic directly in Runner.submit:

```python
def derive_returns_from_price(
    strategy: Strategy,
    *,
    node: str | None = None,
    field: str = "close",
    method: Literal["pct_change", "log_return"] = "pct_change",
) -> list[float]:
    ...
```

- Potential location: `qmtl/runtime/sdk/metrics.py` or similar.
- Responsibilities:
  - Inspect view/node snapshots (e.g., Seamless StreamInput output) to pull the specified `node/field` price series.
  - Compute pct_change or log return per `method`.
  - Reuse **standard price node naming/fields** provided by Expression DAG/Seamless Provider for SR integration.

Implementation details should stay aligned with `auto_derive_returns_proposal.md` and its `derive_returns_from_price_node` direction.

## 6. SR Integration Considerations

- The SR path (`sr_integration_proposal.md`) already depends on Seamless Data Provider and `expression_dag_spec`/`data_spec`.
- Auto-returns in this sketch combines with SR as follows:
  - ExpressionDagBuilder includes **standard price node names/fields** in the DAG.
  - SR templates pass the matching `AutoReturnsConfig` (or `auto_returns=True`) when calling Runner.submit.
- As a result:
  - Simple price-based SR candidates can pass auto-validation without wiring returns, and
  - Complex/production strategies still prefer explicit `returns`/`equity`/`pnl` for precise control.

For eventual implementation:

- Merge the detailed API/utility design from `auto_derive_returns_proposal.md` with this SR-focused sketch, and
- Finalize Runner.submit/ValidationPipeline/WorldService contracts without breaking existing behavior.
