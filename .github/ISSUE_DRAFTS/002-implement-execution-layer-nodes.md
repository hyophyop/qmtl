Title: Implement Execution-Layer Nodes (PreTrade/Sizing/Execution/FillIngest/Portfolio/Risk/Timing)
Labels: feature, execution, sdk, nodes

Summary
Implement the node wrappers specified in the RFC so strategies can attach an exchange Node Set after a signal node.

Tasks
- PreTradeGateNode
  - Wrap `qmtl/sdk/pretrade.py` and integrate `qmtl/common/pretrade.py` reasons.
  - Inputs: activation, providers; Output: pass-through or rejection.
- SizingNode
  - Use `qmtl/sdk/portfolio.py` helpers (value/percent/target_percent).
- ExecutionNode
  - Sim/paper: `qmtl/sdk/execution_modeling.py` + `qmtl/brokerage/*` profile.
  - Live: pass-through OrderPayload to OrderPublishNode.
- OrderPublishNode
  - Reuse existing `TradeOrderPublisherNode` or extend for Node Set metadata.
- FillIngestNode
  - StreamInput consuming `trade.fills` topic; normalize shape to `ExecutionFillEvent`.
- PortfolioNode
  - Apply fills using `Portfolio.apply_fill`; output compacted snapshots.
- RiskControlNode, TimingGateNode
  - Wrap `qmtl/sdk/risk_management.py` and `qmtl/sdk/timing_controls.py`.

Acceptance Criteria
- Unit tests per node (deterministic inputs → outputs).
- Offline simulate path produces fills and updates portfolio.
- Live path can no-op ExecutionNode and rely on FillIngestNode.
- Docs cross-linked from node classes to architecture.

