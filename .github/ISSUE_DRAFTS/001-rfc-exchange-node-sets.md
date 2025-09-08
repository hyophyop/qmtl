Title: RFC: Exchange Node Sets and Feedback Without Cycles
Labels: rfc, architecture, execution

Summary
- Specify how post-signal execution is composed as an exchange-specific Node Set (attachable subgraph) while preserving DAG acyclicity and WS/DM boundaries.

Motivation
- Strategies need realistic execution with feedback (portfolio/risk/timing). Direct cycles violate DM constraints. We need a standard, reusable pattern.

Scope
- Finalize design in docs:
  - docs/architecture/exchange_node_sets.md (added)
  - docs/reference/api/order_events.md (added)
- Define node contracts: PreTradeGateNode, SizingNode, ExecutionNode, OrderPublishNode, FillIngestNode, PortfolioNode, RiskControlNode, TimingGateNode.
- Feedback model: delayed edges (t−1) and/or compacted state topics (trade.portfolio, trade.open_orders).
- WS/DM role boundaries, portfolio scope (strategy vs world), freeze/drain semantics.

Non‑Goals
- WS managing orders/fills/portfolio; DM ingesting broker webhooks.

Design Notes
- Activation gating from WS is enforced; stale → OFF by default.
- Modes: simulate/paper/live with consistent contracts.
- Idempotency: Runner key + server-side key; topic partitioning guidance.

Deliverables
- [x] Architecture doc: exchange_node_sets.md
- [x] Reference event schemas: order_events.md
- [ ] Review and sign-off from owners of Gateway/WS/DM

Acceptance Criteria
- Docs reviewed; responsibilities and data flows unambiguous.
- No changes required to DM core invariants; WS keeps activation-only role.
- Clear extension points for new exchanges.

