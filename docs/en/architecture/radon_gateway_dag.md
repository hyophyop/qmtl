---
title: "Gateway/DAG Control-Plane Radon Plan"
tags: ["radon", "control-plane"]
author: "QMTL Team"
last_modified: 2025-11-13
---

{{ nav_links() }}

# Gateway/DAG Control-Plane Radon Plan

Gateway, DAG Manager, and ControlBus form the contract surface that precedes WorldService and the SDK. As of 2025‑11 multiple D-grade Radon findings were recorded across qmtl/services/gateway/* and qmtl/services/dagmanager/*. This plan reduces those hotspots to A/B grades, restores deterministic contract tests, and clears the runway for the SDK runtime (#1511) and WorldService (#1513) workstreams.

## Findings

| Area | Path | Radon | Notes |
| --- | --- | --- | --- |
| Gateway Health | `gateway_health.get_health` {{ code_url('qmtl/services/gateway/gateway_health.py#L21') }} | D (25) | Health probes, downgrade fallbacks, and HTTP serialization live in one coroutine, masking timeouts |
| Submission FSM | `StrategySubmissionHelper.process` {{ code_url('qmtl/services/gateway/strategy_submission.py#L64') }} | D (22) | DAG diff, TTL pruning, and CommitLog fan-out are interleaved, complicating regression tests |
| ControlBus Bridge | `ControlBusConsumer._handle_message` {{ code_url('qmtl/services/gateway/controlbus_consumer.py#L221') }} | D (25) | Message parsing, retries, and metrics share a monolithic handler |
| DAG Diff service | `DiffServiceServicer.Diff` {{ code_url('qmtl/services/dagmanager/grpc_server.py#L103') }} | D (21) | Stream resumption, topic resolution, and node cache access are fused together |
| Kafka Admin | `_KafkaAdminClient.list_topics` {{ code_url('qmtl/services/dagmanager/server.py#L112') }} | D (21) | Connection wiring, TLS knobs, and retries mix inside the same call |
| Graph repo | `MemoryNodeRepository.get_buffering_nodes` {{ code_url('qmtl/services/dagmanager/node_repository.py#L197') }} | C (12) | Sentinel and buffering checks accumulate branching |

## Goals

- Bring control-plane CC scores down to **A/B across the highlighted modules**; eliminate D-grade paths entirely
- Add **contract tests** for health, submission, and ControlBus flows so SDK ↔ WS behavior stays documented
- Introduce **fail-fast instrumentation** (Prometheus + structured logs) for DAG Manager gRPC/Admin entry points
- Record the baseline and post-change Radon output via `uv run --with radon -m radon cc -s qmtl/services/{gateway,dagmanager}`

## Refactor tracks

### 1. Lightweight health & observability

- Split `get_health` into a collector/adaptor pair. Fan out Redis/Kafka/Neo4j calls through a TimeLimiter and keep the top-level coroutine focused on stitching responses (target CC < 10).
- Embed the MultiWorldRebalanceRequest version flag (issue #1514) inside the health payload so clients discover Gateway compatibility before enabling WS v2.
- Manage those flags via configuration (`gateway.rebalance_schema_version`, `gateway.alpha_metrics_capable`, optional `gateway.compute_context_contract`) to avoid ad-hoc toggles per deployment.
- Add fast unit tests that inject fake collectors and assert timeout fallbacks without aiohttp stacks.

### 2. Submission FSM staging

- Break `StrategySubmissionHelper.process` into three explicit stages (normalize payload → invoke DAG diff → CommitLog fan-out). Wrap each stage with its own async context manager for retries and metrics.
- Move Redis FSM/TTL invalidation into a standalone helper (`SubmissionPersistencePlan`) so DAG retry semantics become testable.
- Author contract tests under `tests/qmtl/services/gateway/test_strategy_submission_contract.py` for single/multi-world payloads and run them with `uv run -m pytest -W error -n auto`.

### 3. ControlBus bridge refactor

- Replace `_handle_message` with a strategy table: parse → validate → side effects (CommitLog/Redis/WS) occur in separate helpers, cutting CC below 10.
- Keep `_broker_loop` responsible for offsets/backpressure while `_handle_message` is near-pure for deterministic replay tests.
- Emit new counters such as `gateway_controlbus_unparsed_total` and `gateway_controlbus_retry_total` from `metrics.py`.

### 4. DAG Diff & Admin hardening

- Separate stream resumption from diff computation by introducing a `DiffExecutionContext` data class and letting `_GrpcStream` deal strictly with gRPC plumbing.
- Extract `_AdminSession` from `_KafkaAdminClient` so TLS/credential wiring is test-injectable and CLI-friendly.
- Flatten the branching inside `MemoryNodeRepository.get_buffering_nodes` by mapping sentinel/buffering predicates explicitly.

### 5. Documentation, contracts, testing

- Cross-link the new structure inside `docs/en/architecture/gateway.md` and `dag-manager.md`; keep this plan as the canonical sourcing note.
- Smoke check via `uv run --with radon -m radon cc -s qmtl/services/gateway qmtl/services/dagmanager | rg ' [CD]'`.
- Regression suite: `uv run -m pytest -W error -n auto tests/qmtl/services/gateway tests/qmtl/services/dagmanager`.

## Timeline & deliverables

| Phase | Duration | Deliverables |
| --- | --- | --- |
| Phase 0 (prep) | 1 day | Baseline Radon snapshot + current contract captures |
| Phase 1 (Gateway) | 3 days | Health collector, staged submission helper, contract tests, Grafana guardrail updates |
| Phase 2 (ControlBus & DAG) | 3 days | ControlBus strategy table, DiffExecutionContext, Kafka Admin session, admin CLI doc updates |
| Phase 3 (Regression) | 2 days | Integrated bench (1k req/s heap cap), `uv run mkdocs build`, doc refresh |

## Dependencies

- SDK runtime (#1511) defines the `alpha_performance` metric key + parser guard; Gateway must surface the compatibility flag once it lands.
- WorldService (#1513) introduces `MultiWorldRebalanceRequest` v2; Gateway needs the gating flag (Phase 1 deliverable) ahead of that rollout.
- Issue #1514’s shared checklist (WS schema note, Gateway compatibility flag, SDK parser update) must read ✅ by the end of Phase 2.
