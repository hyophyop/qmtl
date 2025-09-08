Title: Node Set: Binance Futures (USDT‑M)
Labels: feature, connectors, brokerage, futures, ccxt

Summary
Provide a Futures Node Set via `FuturesCcxtBrokerageClient` with leverage/margin/hedge mode support.

Tasks
- Builder `BinanceFuturesNodeSet.attach(signal_node, world_id, **opts)`
  - Options: `leverage`, `margin_mode` (cross/isolated), `hedge_mode`, `sandbox`.
  - Map `positionSide`, `reduceOnly`, on-the-fly leverage when supported.
- Profiles
  - Futures-friendly brokerage profile (fees/slippage/hours) with configurable maker/taker.
- Examples & Docs
  - `qmtl/examples/brokerage_demo/ccxt_binance_futures_sandbox_demo.py` linkage.

Acceptance Criteria
- Simulate and sandbox examples execute and publish orders; fills are ingested into portfolio snapshots.

