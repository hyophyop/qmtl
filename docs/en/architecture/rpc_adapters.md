---
title: "RPC Adapter Command/Facade Design"
tags:
  - architecture
  - rpc
  - gateway
  - dag-manager
author: "QMTL Team"
last_modified: 2025-11-16
---

{{ nav_links() }}

# RPC Adapter Command/Facade Design

## 0. Purpose and Core Loop Position

- Purpose: Define common design patterns for RPC/service adapters used by Gateway, DAG Manager, WorldService and the Runtime SDK to reduce complexity and duplication.
- Core Loop position: Wraps the internal/external RPC paths used across Core Loop stages (submit, evaluate, activate, rebalance) in explicit Command/Facade layers so architectural boundaries remain clear in code.

## 1. Scope and Background

This document defines common design patterns for RPC/service adapters used by Gateway, DAG Manager, WorldService and the Runtime SDK.

- Meta issue: #1554 RPC/adapter complexity improvements
- Design/common modules: #1581

### 1.1 radon-based target snapshot

Using `uv run --with radon -m radon cc -s -n C qmtl/runtime/sdk qmtl/services/gateway`, the following RPC/adapter-related functions currently have a C grade (as of 2025‑11‑16):

| File | Function | CC grade / score | Role summary |
| --- | --- | --- | --- |
| `services/gateway/world_client.py` | `WorldServiceClient.get_decide` | C / 17 | WorldService decision HTTP call + TTL cache + header/body TTL parsing + error/fallback handling |
| `services/gateway/world_client.py` | `WorldServiceClient._iter_rebalance_payloads` | C / 12 | Generate and expand rebalance payload variants across schema versions |
| `services/gateway/ownership.py` | `OwnershipManager.acquire` | C / 16 | Redis lock acquisition, timeout and error branches combined in one function |
| `services/gateway/strategy_submission.py` | `StrategySubmissionHelper._resolve_queue_map` | C / 11 | Interpret DAG diff results/world context into queue map with fallbacks |
| `services/gateway/controlbus_consumer.py` | `ControlBusConsumer._parse_kafka_message` | C / 15 | Decode, validate and dispatch ControlBus messages |
| `services/gateway/api.py` | `create_app` | C / 18 | Assemble Gateway API, routers, middleware and dependencies |
| `services/gateway/cli.py` | `_main` | C / 18 | CLI argument parsing, environment setup and service bootstrap |

Earlier snapshots also showed C grades for the following paths, which have since been refactored in separate issues:

- `runtime/sdk/gateway_client.GatewayClient.post_strategy` — #1582
- `services/gateway/dagmanager_client.DagManagerClient.diff`, `services/gateway/submission/diff_executor.DiffExecutor.run`, `services/gateway/worker.StrategyWorker._process` — see the workflow orchestration Radon plan.

This document defines Command/Facade, response parser and error mapper patterns that can be applied consistently to these and similar adapters, and serves as a guide for follow-up issues (#1582, #1583, #1584, ...).

## 2. Layered Model

We decompose RPC adapter flows into the following minimal layers:

1. **Request Builder**
   - Takes domain inputs and constructs HTTP/gRPC requests (path, headers, body, gRPC request messages).
   - Stays as a pure function for easier testing, even though formats differ between WorldService, Gateway and DAG Manager.
2. **Command (Transport + Breaker/Retry)**
   - A single command object/function that sends the request built above.
   - Owns circuit breaker, retry, health-check backoff and latency observation.
   - Integrates with `qmtl.foundation.common.AsyncCircuitBreaker`, `BreakerRetryTransport` and similar utilities.
3. **Response Parser**
   - Converts HTTP/gRPC responses into domain results (e.g., `StrategyAck`, queue maps, decision/activation payloads).
   - Performs schema validation and defaulting where appropriate.
4. **Error Mapper**
   - Maps status codes/error codes/exceptions into domain errors (e.g., `{"error": "duplicate strategy"}` or dedicated exceptions).
   - Allows Gateway/WorldService/DAG Manager adapters to share common error policies.
5. **Facade**
   - Public API surface consumed by SDKs or upstream services.
   - Methods like `WorldServiceClient.get_decide`, `DagManagerClient.diff`, `GatewayClient.post_strategy` live here.
   - Facades only orchestrate Request Builder/Command/Response Parser/Error Mapper, keeping their own logic thin.

The goals of this model are:

- Reduce radon CC from C to A/B by shrinking individual units (Request Builder, Command, Parser, Error Mapper, Facade) and tightening tests around each.
- Share retry/error-mapping/logging policies across Gateway/WorldService/DAG Manager so changes are localized.

## 3. Common Module Skeleton

To share Command/Parser/error representations, we introduce a small skeleton in `qmtl/foundation/common/rpc.py`:

```python
from dataclasses import dataclass
from typing import Any, Callable, Generic, Protocol, TypeVar

TResponse = TypeVar("TResponse")
TResult = TypeVar("TResult")

class RpcCommand(Protocol[TResponse]):
    async def execute(self) -> TResponse: ...

class RpcResponseParser(Protocol[TResponse, TResult]):
    def parse(self, response: TResponse) -> TResult: ...

@dataclass(slots=True)
class RpcError:
    message: str
    cause: Exception | None = None
    details: dict[str, Any] | None = None

@dataclass(slots=True)
class RpcOutcome(Generic[TResult]):
    result: TResult | None = None
    error: RpcError | None = None

    @property
    def ok(self) -> bool: ...

async def execute_rpc(
    command: RpcCommand[TResponse],
    parser: RpcResponseParser[TResponse, TResult],
    *,
    on_error: Callable[[Exception], RpcError] | None = None,
) -> RpcOutcome[TResult]: ...
```

Key properties:

- Commands encapsulate "build + send" concerns, while Parsers focus solely on "response → domain result".
- `execute_rpc` centralizes the Command/Parser handshake and removes duplicated try/except blocks from facades/adapters.
- Retry/breaker/metrics remain the responsibility of individual adapters for now and can later be abstracted further if needed.

This skeleton is intended to be used in follow-up issues as follows:

- WorldService: wrap the HTTP call inside `get_decide` as `RpcCommand[httpx.Response]`, and move TTL/cache decisions into a dedicated Parser.
- DAG Manager: wrap diff/tag calls as Commands and move CRC validation/queue-map normalization/namespace application into Parsers/strategies.
- Gateway SDK: `GatewayClient.post_strategy` already uses helper-based parsing; it can be wrapped as a Parser if/when we align it with this pattern.

## 4. Command/Facade Application Guide

### 4.1 WorldServiceClient.get_decide (Sub-issue #1583)

Target: `qmtl/services/gateway/world_client.py:WorldServiceClient.get_decide`.

- **Request Builder**: use `world_id` and headers to build the `/worlds/{world_id}/decide` URL and request options.
- **Command**: encapsulate `_transport.request("GET", url, headers=headers)` as an `RpcCommand[httpx.Response]` implementation.
- **Response Parser**:
  - Parse TTL from `Cache-Control` header.
  - Parse envelope `ttl` and handle invalid formats.
  - Apply `augment_decision_payload`.
- **Error Mapper**:
  - Define cache fallback policy (`TTLCache`) on network errors/5xx.
  - Decide how to surface errors when no cached value is present.
- **Facade** (`get_decide`):
  - Orchestrate cache lookup → Command/Parser execution → cache update/fallback → return `(payload, stale)`.

### 4.2 DAG diff path (Sub-issue #1584)

Target: `DagManagerClient.diff` → `DiffExecutor.run` → `StrategyWorker._diff_strategy`.

- **Request Builder**: continue to build `DiffNamespace` and `DiffRequest` as today, but make the inputs/outputs explicit.
- **Command**:
  - Wrap `DiffStreamClient.collect` inside an `RpcCommand[dagmanager_pb2.DiffChunk]`.
  - Own circuit breaker and `_collect_with_retries` retry/health-check behavior.
- **Response Parser / strategies**:
  - Treat `DiffRunStrategy` (`QueueMapAggregationStrategy`, `SingleWorldStrategy`) as high-level Parsers that perform CRC validation, sentinel handling and queue-map normalization.
- **Facade**:
  - Keep `StrategyWorker._diff_strategy` responsible only for executing the Command, logging failures, emitting alerts and driving state transitions.

## 5. Migration Strategy and Completion Criteria

### 5.1 Phased migration

1. **Introduce common skeleton (this issue #1581)**
   - Add `qmtl/foundation/common/rpc.py` with Command/Parser/Outcome types and `execute_rpc` helper.
   - Add a small unit test in `tests/qmtl/foundation/common/test_rpc.py` to verify basic success/failure behavior.
2. **Representative PoC paths (#1582, #1583)**
   - Gateway SDK: refactor the `GatewayClient.post_strategy` path to use helper-based parsing/error mapping (already improved in #1582).
   - WorldService: refactor `get_decide` into Command/Parser layers and fully document TTL/cache behavior.
3. **DAG diff path cleanup (#1584)**
   - Separate diff execution/retry/CRC validation/queue-map normalization and treat `DiffRunStrategy` as Parser/strategy objects.
4. **Extend to additional RPC adapters**
   - Gradually apply the pattern to rebalancing, ControlBus consumer, Strategy submission and similar adapters.

### 5.2 Completion criteria

- Command/Facade/Parser/Error Mapper responsibilities are defined here and backed by representative sub-issues for WorldService, DAG diff and SDK paths.
- `qmtl/foundation/common/rpc.py` is merged and used directly or indirectly by at least one of the sub-issues (#1582, #1583, #1584).
- The number of C-grade RPC adapter functions decreases, or remaining C-grade functions are clearly justified and documented via this pattern.

## 6. Checklist

- [x] Collect C-grade RPC adapter functions from radon CC reports.
- [x] Define the Command/Facade/Parser/Error Mapper layer model.
- [x] Introduce the common skeleton module (`qmtl/foundation/common/rpc.py`) and unit tests.
- [ ] Apply the pattern to representative paths in WorldService/SDK/DAG diff (#1582, #1583, #1584).

Related issues
- #1554
- #1581
- #1582
- #1583
- #1584

## 7. Workflow orchestration radon record (moved from maintenance)

This section consolidates the workflow orchestration radon plan into the architecture guide so future orchestration changes keep a single reference point. Prior Control-Plane/Runtime SDK radon plans were retired after their status was folded into this record.

### 7.1 Scope
- Target modules:
  - `qmtl/services/dagmanager/diff_service.py`, `kafka_admin.py`
  - `qmtl/services/gateway/strategy_submission.py`, `dagmanager_client.py`, `worker.py`
  - `qmtl/runtime/sdk/gateway_client.py`, `tag_manager_service.py`, `backfill_engine.py`, `activation_manager.py`
- Related issues:
  - #1549 Workflow orchestration complexity review (meta)
  - #1563 DiffService queue/sentinel orchestration refactor
  - #1564 KafkaAdmin topic verification/creation orchestration cleanup
  - #1565 Gateway strategy submission context/queue-map/world binding pipeline refactor
  - #1566 Gateway DAG diff worker and gRPC client orchestration cleanup
  - #1567 Runtime SDK Gateway/tag/backfill/activation orchestration cleanup

### 7.2 Baseline radon snapshot (at plan time)

The following functions had C/D-level cyclomatic complexity in the radon report while sitting on critical orchestration paths for DAG diff, topic orchestration, strategy submission and Runtime SDK flows.

| File | Function | CC grade / score | Notes |
| --- | --- | --- | --- |
| `services/dagmanager/server.py` | `_KafkaAdminClient.list_topics` | D / 21 | Topic metadata lookup, validation and error handling combined. |
| `services/dagmanager/diff_service.py` | `DiffService._hash_compare` | C / 20 | Queue binding, cross-context validation, sentinel/CRC/metrics in a single method. |
| `services/dagmanager/kafka_admin.py` | `KafkaAdmin._verify_topic` | C / 13 | Topic existence/collision/parameter checks mixed with error flow. |
| `services/gateway/strategy_submission.py` | `StrategySubmissionHelper._build_queue_outputs` | C / 14 | Diff call, fallback queue map and CRC sentinel handled in one orchestration method. |
| `services/gateway/strategy_submission.py` | `StrategySubmissionHelper._persist_world_bindings` | C / 12 | DB and WorldService bindings and error handling intertwined. |
| `services/gateway/dagmanager_client.py` | `DagManagerClient.diff` | C / 11 | Builds the request, collects the gRPC stream, validates CRC, handles retries/breaker and applies namespaces. |
| `services/gateway/worker.py` | `StrategyWorker._process` | C / 14 | Redis state loading, diff call, FSM transitions, WS broadcasting and alerts in one function. |
| `runtime/sdk/trade_dispatcher.py` | `TradeOrderDispatcher.dispatch` | C / 20 | Validation, gating, dedup and HTTP/Kafka submission handled together. |
| `runtime/sdk/gateway_client.py` | `GatewayClient.post_strategy` | C / 14 | HTTP request construction, breaker, status-code mapping and pydantic validation combined. |
| `runtime/sdk/tag_manager_service.py` | `TagManagerService.apply_queue_map` | C / 16 | Queue-map application, logging and state updates tightly coupled. |
| `runtime/sdk/backfill_engine.py` | `BackfillEngine._publish_metadata` | C / 17 | Metadata construction, validation and Gateway call in one method. |
| `runtime/sdk/activation_manager.py` | `ActivationManager.start` | C / 14 | Activation start, event stream subscription and initial state orchestration in a single method. |

### 7.3 Outcome summary (as of 2025-11-16)

After merging the work from #1563–#1567, the CC grades for the paths above improved as follows.

- DAG Manager
  - `_KafkaAdminClient.list_topics` (D / 21) → **A / 2** (#1563).
  - `DiffService._hash_compare` (C / 20) → **A / 1** (#1563) — topic binding planning/execution split with result types.
  - `KafkaAdmin._verify_topic` (C / 13) → **A / 1** (#1564) — introduced `TopicVerificationPolicy` and `TopicEnsureResult`.
- Gateway
  - `StrategySubmissionHelper._build_queue_outputs` (C / 14) → **A / 3** (#1565) — refactored around `QueueResolution` and `_resolve_queue_map`.
  - `StrategySubmissionHelper._persist_world_bindings` (C / 12) → **A / 3** (#1565) — separated binding target discovery from WorldService sync.
  - `DagManagerClient.diff` (C / 11) → **A / 3** (#1566) — delegated stream collection, CRC checks and namespace application to `DiffStreamClient`.
  - `StrategyWorker._process` (C / 14) → **A / 4** (#1566) — split into smaller steps for locking, context loading, diff execution, broadcasting and FSM transitions.
- Runtime SDK
  - `TradeOrderDispatcher.dispatch` (C / 20) → **A / 3** — now a pipeline of `DispatchStep` implementations.
  - `GatewayClient.post_strategy` (C / 14) → **A / 1** (#1567) — introduced `GatewayCallResult` and split `_post` / `_parse_strategy_response`.
  - `TagManagerService.apply_queue_map` (C / 16) → **A / 3** (#1567) — separated match collection, application and logging helpers.
  - `BackfillEngine._publish_metadata` (C / 17) → **A / 5** (#1567) — split metadata construction and Gateway submission into dedicated helpers.
  - `ActivationManager.start` (C / 14) → **A / 5** (#1567) — decomposed startup into `_start_existing_client`, `_start_via_gateway`, `_schedule_polling` and related helpers.

Some C-grade functions remain in other modules, but this section is scoped to the orchestration paths above. The data normalization/backfill track reached A/B grades in the 2025-12-02 radon scan, so that dedicated radon plan has been retired; rerun the normalization/backfill radon checks directly if regressions appear. The WorldService schema/alpha track finished under #1514 and rolled into `architecture/worldservice.md` and `world/rebalancing.md`, retiring the separate radon plan.

### 7.4 Common anti-patterns

Before the refactors, orchestration paths often exhibited the following anti-patterns.

- Single methods handled validation → external calls → retry/backoff → result merging → error handling → metrics/logging, driving CC to C/D grades.
- Network/broker/WorldService error handling and downgrade rules were modeled as nested `if`/`try` blocks, making the happy path hard to see and tests coarse-grained.
- Retry policies, logging formats and error mappings were duplicated across modules, increasing synchronization cost for changes.
- Success/partial-success/failure was expressed via a mix of booleans, `None` values, exceptions and ad-hoc `dict` error payloads, leading to inconsistent branching at call sites.

### 7.5 Applied patterns / design direction

To address the anti-patterns above, the following patterns were applied across the scope of #1549.

- **Pipeline / Chain of Responsibility**
  - Components such as `TradeOrderDispatcher`, `StrategySubmissionHelper` and `StrategyWorker` now follow a step-based pipeline where small step objects/methods (for example `ComputeContextStep`, `DiffQueueMapStep`, `WorldBindingPersistStep`) each own a single concern and the main orchestrator manages sequence only.
- **Explicit Result types**
  - Result objects like `GatewayCallResult`, `StrategySubmissionResult`, `DiffOutcome`, `QueueResolution` and `TopicEnsureResult` model success/partial-success/failure and diagnostics explicitly.
  - Callers can branch on a single `ok` flag or well-defined fields instead of mixing booleans, exceptions and `None` checks.
- **Shared helpers/decorators**
  - Kafka topic verification/creation (`TopicVerificationPolicy`, `TopicCreateRetryStrategy`), DAG diff streaming (`DiffStreamClient`), Gateway HTTP calls (`GatewayClient._post`) and WorldService context merging (`ComputeContextService`) were factored into helper layers.
  - Orchestration methods now primarily compose these helpers rather than implementing low-level control flow.
- **Explicit downgrade/fallback modeling**
  - Diff failure → TagQuery fallback, CRC sentinel fallback and WorldService stale/unavailable downgrade flows are represented via Result types and dedicated helper methods so the policies are visible and testable.

### 7.6 Validation checklist

- Radon complexity / MI
  - `uv run --with radon -m radon cc -s qmtl/services/dagmanager/diff_service.py qmtl/services/dagmanager/kafka_admin.py`
  - `uv run --with radon -m radon cc -s qmtl/services/gateway/strategy_submission.py qmtl/services/gateway/dagmanager_client.py qmtl/services/gateway/worker.py`
  - `uv run --with radon -m radon cc -s qmtl/runtime/sdk/gateway_client.py qmtl/runtime/sdk/tag_manager_service.py qmtl/runtime/sdk/backfill_engine.py qmtl/runtime/sdk/activation_manager.py`
  - Optionally, full snapshot: `uv run --with radon -m radon cc -s -n C qmtl/services/dagmanager qmtl/services/gateway qmtl/runtime/sdk`
- Regression tests
  - `uv run -m pytest -W error -n auto qmtl/services/dagmanager qmtl/services/gateway qmtl/runtime/sdk`
- Docs build
  - `uv run mkdocs build`

With this work and the checklist above, the workflow orchestration complexity review in #1549 is considered complete.

### 7.7 Relation to RPC adapter plan (#1554, #1584)

- The DAG diff execution path (`DagManagerClient.diff` → `DiffExecutor.run` → `StrategyWorker._diff_strategy`) already follows the patterns described above and now has A/B radon grades.
- The RPC adapter Command/Facade design (#1554, #1581, #1584) treats this path as a representative example; see this document for the layered breakdown.
- Issue #1584 focuses on aligning the RPC adapter plan with this existing design and marking the diff path as complete under the #1554 meta issue, without additional structural changes.
