Title: Portfolio Scope Option (Strategy vs World) and Cross‑Strategy Risk
Labels: architecture, risk, execution

Summary
Introduce an explicit portfolio scope option for Exchange Node Sets: strategy‑scoped (default) or world‑scoped. Define cross‑strategy risk constraints when world‑scoped.

Tasks
- Scope parameter plumbing through Node Set builders and PortfolioNode keys.
- RiskControlNode: support portfolio‑level concentration/leverage across strategies under world‑scope.
- Docs: Update `docs/architecture/exchange_node_sets.md` with scope implications and examples.

Acceptance Criteria
- Deterministic keys for snapshots and fills under both scopes.
- Tests for sharing portfolio across two strategies in the same world.

