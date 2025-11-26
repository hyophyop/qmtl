# [Home](../index.md) / [world](index.md) / [world_todo](world_todo.md)

# QMTL Strategy State Management — Draft

Overview

Design the lifecycle from submission through validation to live operation. Only
strategies that pass sufficient simulation should trade live. Worlds group
strategies and apply policies to automate state transitions. Legacy
`--mode`/`backtest|dry-run|live` APIs are removed; execution follows WS decisions
via `Runner.submit(world=...)` (Gateway URL via `QMTL_GATEWAY_URL`) or local
`Runner.submit(mode="backtest")`.

- World: portfolio scope and policy owner
- Strategy: user‑submitted trading logic
- Node: DAG compute unit for inputs/processing/execution

State definitions (Nodes, Strategies, Worlds)

Nodes
- Initialized: created, before run
- Pre‑Warmup: waiting until `period` worth of input exists; no output yet
- Active: executing with required inputs
- Completed: finished over a finite window (offline validation)
- Error: halted due to failures; propagate flags upstream; allow restart

Strategies
- Submitted/Initialized: accepted and queued by the system
- Validation/Simulation: backtest/offline run computing performance metrics
- Operational under WS: orders gated by activation; stale/unknown decisions gate OFF
- Evaluating: determines promotion readiness (often overlaps dry‑run)

Worlds
- evaluating / applying / steady — minimal ops states

The rest of this document enumerates the policy structure, CLI/API surfaces,
automatic transition flows, and work items for implementation.
