Title: Runner: Optional Pre‑Trade Chain Toggle + Metrics Standardization
Labels: sdk, runner, feature

Summary
Add an opt-in Runner flag to pass `TradeOrderPublisherNode` outputs through a default pre‑trade chain (Activation → PreTrade → Timing → Sizing) before routing, and standardize metrics.

Tasks
- Runner flag (env or API): `QMTL_PRETRADE_CHAIN=on` (default off)
- Chain components
  - ActivationManager already enforced; expose reason codes on block.
  - Call `check_pretrade(...)` and emit rejection metrics.
  - Timing gate via `TimingController.validate_timing` with override hints.
- Metrics
  - Counters for attempts/rejections by `RejectionReason`.
  - Latency histograms for order processing and webhook ingestion.

Acceptance Criteria
- Backward compatible (off by default).
- Unit tests: blocked orders do not route; reasons recorded.

