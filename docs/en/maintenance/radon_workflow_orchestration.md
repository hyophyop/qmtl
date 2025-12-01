# Workflow Orchestration Radon Plan

## Scope
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

This document summarizes the outcome of the workflow orchestration complexity work tracked in the issues above and captures reusable design patterns for future changes.
Scope note (2025-11-24): this page is now the canonical radon record for Gateway + DAG Manager + Runtime SDK orchestration. The earlier Control-Plane and Runtime SDK radon plan documents have been retired and their status rolled into this page.

## Baseline radon snapshot (at plan time)

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

## Outcome summary (as of 2025-11-16)

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

Some C-grade functions remain in other modules, but this document is scoped to the orchestration paths above. Data normalization/backfill work continues under `maintenance/radon_normalization_backfill.md`, and the WorldService schema/alpha track finished under #1514 and rolled into `architecture/worldservice.md` and `world/rebalancing.md`, retiring the separate radon plan.

## Common anti-patterns

Before the refactors, orchestration paths often exhibited the following anti-patterns.

- Single methods handled **validation → external calls → retry/backoff → result merging → error handling → metrics/logging**, driving CC to C/D grades.
- Network/broker/WorldService error handling and downgrade rules were modeled as nested `if`/`try` blocks, making the happy path hard to see and tests coarse-grained.
- Retry policies, logging formats and error mappings were duplicated across modules, increasing synchronization cost for changes.
- Success/partial-success/failure was expressed via a mix of booleans, `None` values, exceptions and ad-hoc `dict` error payloads, leading to inconsistent branching at call sites.

## Applied patterns / design direction

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

## Validation checklist

The following checklist is recommended when modifying workflow orchestration paths in this scope.

- radon complexity / MI
  - `uv run --with radon -m radon cc -s qmtl/services/dagmanager/diff_service.py qmtl/services/dagmanager/kafka_admin.py`
  - `uv run --with radon -m radon cc -s qmtl/services/gateway/strategy_submission.py qmtl/services/gateway/dagmanager_client.py qmtl/services/gateway/worker.py`
  - `uv run --with radon -m radon cc -s qmtl/runtime/sdk/gateway_client.py qmtl/runtime/sdk/tag_manager_service.py qmtl/runtime/sdk/backfill_engine.py qmtl/runtime/sdk/activation_manager.py`
  - Optionally, full snapshot: `uv run --with radon -m radon cc -s -n C qmtl/services/dagmanager qmtl/services/gateway qmtl/runtime/sdk`
- Regression tests
  - `uv run -m pytest -W error -n auto qmtl/services/dagmanager qmtl/services/gateway qmtl/runtime/sdk`
- Docs build
  - `uv run mkdocs build`

With this work and the checklist above, the workflow orchestration complexity review in #1549 is considered complete.

### Relation to RPC adapter plan (#1554, #1584)

- The DAG diff execution path (`DagManagerClient.diff` → `DiffExecutor.run` → `StrategyWorker._diff_strategy`) already follows the patterns described above and now has A/B radon grades.
- The RPC adapter Command/Facade design (#1554, #1581, #1584) treats this path as a representative example; see `architecture/rpc_adapters.md` for the layered breakdown.
- Issue #1584 focuses on aligning the RPC adapter plan with this existing design and marking the diff path as complete under the #1554 meta issue, without additional structural changes.
