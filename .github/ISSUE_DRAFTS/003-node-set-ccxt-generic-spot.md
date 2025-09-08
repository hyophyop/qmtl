Title: Node Set: CCXT Generic (Spot)
Labels: feature, connectors, brokerage, ccxt

Summary
Provide a ready-made Node Set builder for spot exchanges via CCXT, parameterized by exchange id and credentials.

Tasks
- Builder `CcxtSpotNodeSet.attach(signal_node, world_id, **opts)`
  - Wires the standard nodes with CCXT `CcxtBrokerageClient`.
  - Options: `sandbox`, `apiKey/secret`, `time_in_force`, reduceOnly support where applicable.
- Profiles
  - Choose sensible defaults for `qmtl/brokerage` profile (slippage/fees/hours).
- Examples & Docs
  - Example strategy in `qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py`.
  - Guidance in docs: link to `docs/architecture/exchange_node_sets.md`.

Acceptance Criteria
- Demo runs in simulate and (optionally) sandbox live mode with environment vars.
- Clear failure modes for missing credentials.

