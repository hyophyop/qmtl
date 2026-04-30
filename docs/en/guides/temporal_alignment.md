# Temporal Alignment

Temporal alignment is an SDK feature for turning inputs with different timing semantics, such as daily bars, hourly bars, and order book snapshots, into one aligned payload stream. Existing `align_frames()` keeps the shared timestamp intersection; temporal alignment uses a trigger timestamp to perform exact/as-of/temporal lookups and returns freshness status with the selected payloads.

## Basic pattern

```python
from qmtl.runtime.sdk import (
    AlignmentInputSpec,
    ProcessingNode,
    StreamInput,
    TemporalAlignedOutputSpec,
    TemporalSpec,
)

daily = StreamInput(
    tags=["krx", "daily"],
    interval="1d",
    period=1,
    temporal=TemporalSpec(kind="bar"),
    alignment=AlignmentInputSpec(alias="daily", partition_key="symbol"),
)
hourly = StreamInput(
    tags=["krx", "hourly"],
    interval="1h",
    period=1,
    temporal=TemporalSpec(kind="bar"),
    alignment=AlignmentInputSpec(alias="hourly", partition_key="symbol"),
)
book = StreamInput(
    tags=["krx", "book"],
    interval="1s",
    period=1,
    temporal=TemporalSpec(kind="event", idle_after="2s", sequence="seq"),
    alignment=AlignmentInputSpec(alias="book", partition_key="symbol"),
)

market_context = ProcessingNode(
    input=[daily, hourly, book],
    output=TemporalAlignedOutputSpec(trigger=book, partition_key="symbol"),
    interval="1s",
    period=1,
)

signal = ProcessingNode(
    input=market_context,
    compute_fn=lambda view: make_signal(
        view.window(market_context, market_context.interval, count=1).latest()
    ),
    interval="1s",
    period=1,
)
```

- Use `TemporalSpec(kind="bar")` for bar inputs such as daily or hourly bars.
- Use `TemporalSpec(kind="event")` for irregular event inputs such as order book snapshots.
- `AlignmentInputSpec(alias=...)` names each input inside the aligned payload.
- A `ProcessingNode` with `TemporalAlignedOutputSpec` emits aligned payloads on trigger input arrival without a user `compute_fn`.
- When `StreamInput` carries `temporal` metadata, `JoinSpec` is inferred automatically. If inference is ambiguous, QMTL raises instead of running with missing policy.
- Bar inputs infer to `asof` with `closed_only=True`, excluding payloads with `is_final=False`.
- Trigger inputs infer to `exact`.
- Non-trigger event/state inputs require one of `idle_after`, `max_age`, or `tolerance`; otherwise unbounded as-of would be unsafe and inference raises.
- `tolerance` or `max_age` marks stale selected inputs through `aligned.ready=False` and `stale_inputs`. With default `ready_only=True`, not-ready payloads are not emitted downstream.
- Use `partition_key` with `partition={"symbol": "005930"}` to align a multi-symbol input by symbol.
- Use targeted overrides such as `overrides={"book": {"max_age": "500ms"}}` when the inferred default is not right. Passing explicit `JoinSpec` values remains supported as the low-level escape hatch.

## Korean equity validation scenarios

- Daily trend + hourly filter + current order book entry: use the order book timestamp as the trigger and look up daily/hourly inputs with `asof` over completed bars.
- Hourly close rebalance + recent order book execution price: use the hourly close timestamp as the trigger and read the order book with bounded `asof`.
- Session-open gap strategy: use session open or first quote as the trigger and read the previous daily bar with temporal lookup.
- Order-book-driven market making + daily/hourly regime filter: separate fast order book triggers from slower bar context through freshness status.
- Holiday, halt, VI, or order book idle handling: read market-status streams/tables as temporal references.
- Multi-symbol ranking + symbol-level order book liquidity filter: use `partition_key` and optional inputs so one delayed symbol does not block the whole universe.
- Corporate action or revised daily bars: live/paper should side-output or drop late data, while backtest/simulate may recompute deterministically.

## Scope

Temporal alignment does not change the `NodeCache` storage model. Detailed KRX rules such as holidays, auction phases, and trading halts should be supplied by calendar/session adapters rather than hard-coded in core. For v1, order book deltas should be normalized by a provider or NodeSet into validated snapshot/state streams before temporal alignment consumes them.
