---
title: "QMTL Gateway — Comprehensive Technical Specification"
tags: []
author: "QMTL Team"
last_modified: 2025-09-22
spec_version: v1.2
---

{{ nav_links() }}

# QMTL Gateway — Comprehensive Technical Specification

*Research‑Driven Draft v1.2 — 2025‑06‑10*

## 관련 문서
- [Architecture Overview](README.md)
- [QMTL Architecture](architecture.md)
- [DAG Manager](dag-manager.md)
- [WorldService](worldservice.md)
- [ControlBus](controlbus.md)
- [Lean Brokerage Model](lean_brokerage_model.md)

추가 참고
- 운영 가이드: [리스크 관리](../operations/risk_management.md), [타이밍 컨트롤](../operations/timing_controls.md)
- 레퍼런스: [Brokerage API](../reference/api/brokerage.md), [Commit‑Log 설계](../reference/commit_log.md), [World/Activation API](../reference/api_world.md)

> This extended edition enlarges the previous document by ≈ 75 % and adopts an explicit, graduate‑level rigor. All threat models, formal API contracts, latency distributions, and CI/CD semantics are fully enumerated.
> Legend: **Sx** = Section, **Rx** = Requirement, **Ax** = Assumption.

---

## S0 · System Context & Goals

Gateway sits at the **operational boundary** between *ephemeral* strategy submissions and the *persistent* graph state curated by DAG Manager. Its design objectives are:

| ID     | Goal                                                         | Metric                    |
| ------ | ------------------------------------------------------------ | ------------------------- |
|  G‑01  | Diff submission queuing **loss‑free** under 1 k req/s burst  | `lost_requests_total = 0` |
|  G‑02  | **≤ 150 ms** p95 end‑to‑end latency (SDK POST → Warm‑up ack) | `gateway_e2e_latency_p95` |
|  G‑03  | Zero duplicated Kafka topics across concurrent submissions   | invariants §S3            |
|  G‑04  | Line‑rate WebSocket streaming of state updates (≥ 500 msg/s) | WS load test              |

**Ax‑1** SDK nodes adhere to canonical hashing rules (see Architecture doc §1.1).
**Ax‑2** Neo4j causal cluster exposes single‑leader consistency; read replicas may lag.
**Ax‑3** Gateway forwards a compute context `{ world_id, execution_domain, as_of, partition }` to downstream services. DAG Manager uses it to derive a Domain‑Scoped ComputeKey; WorldService uses it to authorize/apply domain policies.

### Non‑Goals
- Gateway does not compute world policy decisions and is not an SSOT for worlds or queues.
- Gateway does not manage brokerage execution; it only mediates requests and relays control events.

---

## S1 · Functional Decomposition

```mermaid
graph LR
    subgraph Client Tier
       SDK["Strategy SDK"]
    end
    subgraph Gateway Tier
       Ingest[/REST Ingest/]
       FIFO["FIFO Queue (Redis)"]
       Worker["Async Worker"]
       FSM["Redis FSM Store"]
       WS["WebSocket Hub"]
    end
    subgraph Core Tier
    DAGM["DAG Manager gRPC"]
    KAFKA[(Kafka/Redpanda)]
end
SDK --> Ingest --> FIFO --> Worker --> DAGM
DAGM --> Worker --> FSM --> WS --> SDK
Worker -->|topic map| SDK
DAGM-.->|queue events|Ingest
```

Note: WorldService and ControlBus are omitted in this decomposition for brevity. See §S6 for the Worlds proxy and opaque event stream handoff. In the full system, Gateway subscribes to ControlBus and proxies WorldService APIs.

---

## S2 · API Contract (**OpenAPI 3.1 excerpt**)

```yaml
paths:
  /strategies:
    post:
      summary: Submit local DAG for execution
      requestBody:
        content:
          application/json:
            schema: { $ref: '#/components/schemas/StrategySubmit' }
      responses:
        '202': { $ref: '#/components/responses/Ack202' }
  /strategies/{id}/status:
    get:
      parameters:
        - in: path
          name: id
          schema: { type: string }
      responses:
        '200': { $ref: '#/components/responses/Status200' }
  /queues/by_tag:
    get:
      summary: Fetch queues matching tags and interval
      parameters:
        - in: query
          name: tags
          schema: { type: string }
        - in: query
          name: interval
          schema: { type: integer }
        - in: query
          name: match_mode
          schema: { type: string, enum: [any, all] }
          description: |
            Preferred tag matching mode.
      responses:
        '200':
          description: Queue list
          content:
            application/json:
              schema:
                type: object
                properties:
                  queues:
                    type: array
                    items:
                      type: object
                      properties:
                        queue: { type: string }
                        global: { type: boolean }
```
Clients SHOULD specify ``match_mode`` to control tag matching behavior. When
omitted, Gateway defaults to ``any`` for backward compatibility.

**Example Request (compressed 32 KiB DAG JSON omitted)**

```http
POST /strategies HTTP/1.1
Authorization: Bearer <jwt>
Content‑Encoding: gzip
Content‑Type: application/json
{
  "dag_json": "<base64>",
  "meta": {
    "user": "quant.alice",
    "desc": "BTC scalper",
    "execution_domain": "backtest",
    "as_of": "2025-01-01T00:00:00Z",
    "partition": "tenant-a"
  },
  "world_ids": ["crypto_mom_1h", "crypto_alt_1h"]  // or legacy single field: "world_id"
}
```

> **Backtests & dry-runs:** When `meta.execution_domain` resolves to `backtest` or
> `dryrun` (including aliases such as `compute-only`, `paper`, or `sim`), callers
> MUST include `meta.as_of`. Gateway downgrades missing values to compute-only
> backtests and records the event via `strategy_compute_context_downgrade_total{
> reason="missing_as_of"}` to prevent dataset cross-contamination.

**Example Queue Lookup**

```http
GET /queues/by_tag?tags=t1,t2&interval=60&match_mode=any HTTP/1.1
Authorization: Bearer <jwt>
```

| HTTP Status         | Meaning                                 | Typical Cause      |
| ------------------- | --------------------------------------- | ------------------ |
|  202 Accepted       |  Ingest successful, StrategyID returned | Nominal            |
|  400 Bad Request   |  CRC mismatch between SDK and Gateway  | NodeID CRC failure  |
|  409 Conflict       |  Duplicate StrategyID within TTL        | Same DAG re‑submit |
|  422 Unprocessable  |  Schema validation failure              | DAG JSON invalid    |

---

## S3 · Exactly‑Once Execution (Node×Interval×Bucket)

This section summarizes the once‑and‑only‑once layer required by issue #544.

- Ownership: For each execution key `(node_id, interval, bucket_ts)`, a single worker acquires ownership before executing. Gateway uses a DB advisory lock (Postgres `pg_try_advisory_lock`) with optional Kafka‑based coordination.
- Commit log: Results are published via a transactional, idempotent Kafka producer to a compacted topic. The message value is `(node_id, bucket_ts, input_window_hash, payload)`.
- Message key: The Kafka message key is built as `"{partition_key(node_id, interval, bucket_ts)}:{input_window_hash}"` ensuring compaction on a stable prefix while preserving uniqueness per input window.
- Deduplication: Downstream consumers deduplicate on the triple `(node_id, bucket_ts, input_window_hash)` and increment `commit_duplicate_total` when duplicates are observed.
- Owner handoff metric: Gateway increments `owner_reassign_total` when a different worker takes ownership of the same execution key mid‑bucket (best‑effort reporting).

Acceptance tests cover: (a) two workers competing for the same key yield exactly one commit with zero duplicates, and (b) owner takeover increments `owner_reassign_total` once.


## S3 · Deterministic FIFO & Idempotency

**Invariant R‑3.1** At most one Worker may pop a given StrategyID. Implemented by:
`SETNX("lock:{id}", worker_id, "NX", "PX", 60000)`

### S4 · Architecture Alignment

The architecture document (§3) defines the deterministic NodeID used across Gateway and DAG Manager. Each NodeID is computed as `blake3:<digest>` over the **canonical serialization** of `(node_type, interval, period, params(split & canonical), dependencies(sorted by node_id), schema_compat_id (stable across minor/patch), code_hash)`. Non-deterministic fields are excluded; the `blake3:` prefix is mandatory, and BLAKE3 XOF may be used for strengthening. Gateway must generate the same IDs before calling the DiffService.

Clarifications
- NodeID MUST NOT include `world_id`. World isolation is enforced at the WVG layer and via world-scoped queue namespaces (e.g., `topic_prefix`), not in the global ID.
- TagQueryNode canonicalization: do not include the dynamically resolved upstream queue set in `dependencies`. Instead, capture the query spec in `params_canon` (normalized `query_tags` sorted, `match_mode`, and `interval`). Runtime queue discovery and growth are delivered via ControlBus → SDK TagQueryManager; NodeID remains stable across discoveries.
- Gateway rejects any node submission missing the hash tuple `(node_type, code_hash, config_hash, schema_hash)` with `E_NODE_ID_FIELDS` and returns `E_NODE_ID_MISMATCH` when the provided `node_id` does not equal the canonical `compute_node_id()` output. Both errors include actionable hints so SDK clients can regenerate DAGs with the BLAKE3 contract.

Immediately after ingest, Gateway inserts a `VersionSentinel` node into the DAG so that rollbacks and canary traffic control can be orchestrated without strategy code changes. This behaviour is enabled by default and controlled by the ``insert_sentinel`` configuration field; it may be disabled with the ``--no-sentinel`` CLI flag.

Gateway persists its FSM in Redis with AOF enabled and mirrors crucial events in PostgreSQL's Write-Ahead Log. This mitigates the Redis failure scenario described in the architecture (§2).

When resolving `TagQueryNode` dependencies, the Runner's **TagQueryManager**
invokes ``resolve_tags()`` which issues a ``/queues/by_tag`` request. Gateway
consults DAG Manager for queues matching `(tags, interval)` and returns the list
so that TagQueryNode instances remain network‑agnostic and only nodes lacking
upstream queues execute locally.

Gateway also listens (via ControlBus) for `sentinel_weight` CloudEvents emitted by DAG Manager. Upon receiving an update, the in-memory routing table is adjusted and the new weight broadcast to SDK clients via WebSocket. The effective ratio per version is exported as the Prometheus gauge `gateway_sentinel_traffic_ratio{version="<id>"}`.

### S5 · Reliability Checklist

* **NodeID CRC 파이프라인** – SDK가 전송한 `node_id`와 Gateway가 재계산한 값이
  diff 요청 및 응답의 `crc32` 필드로 상호 검증된다. CRC 불일치가 발생하면 HTTP 400으로 반환된다.
* **TagQueryNode 런타임 확장** – Gateway가 새 `(tags, interval)` 큐를 발견하면
  `tagquery.upsert` CloudEvent를 발행하고 Runner의 **TagQueryManager**가 이를
  수신해 노드 버퍼를 자동 초기화한다.
* **Local DAG Fallback Queue** – DAG Manager가 응답하지 않을 때 제출된 전략 ID는
  메모리에 임시 저장되며 서비스가 복구되면 Redis 큐로 플러시된다.
* **Sentinel Traffic Δ 확인 루프** – `traffic_weight` 변경 후 Gateway 라우팅
  테이블과 SDK 로컬 라우터가 5초 이내 동기화됐는지를 `sentinel_skew_seconds`
  지표로 측정한다.

### Gateway CLI Options

Run the Gateway service. The ``--config`` flag is optional:

```bash
# start with built-in defaults
qmtl gw

# specify a configuration file
qmtl gw --config qmtl/examples/qmtl.yml
```

When provided, the command reads the ``gateway`` section of
``qmtl/examples/qmtl.yml`` for all server parameters. Omitting ``--config``
starts the service with built-in defaults that use SQLite and an in-memory
Redis substitute. The sample file illustrates how to set ``redis_dsn`` to point
to a real cluster. If ``redis_dsn`` is omitted, Gateway automatically uses the
in-memory substitute. See the file for a fully annotated configuration template.
Setting ``insert_sentinel: false`` disables automatic ``VersionSentinel`` insertion.

Available flags:

- ``--config`` – optional path to configuration file.
- ``--no-sentinel`` – disable automatic ``VersionSentinel`` insertion.
- ``--allow-live`` – disable the live trading guard requiring ``X-Allow-Live: true``.

---

## S4 · Ownership & Commit‑Log Design

- **Ownership** — Gateway는 제출 요청 큐(FIFO)와 전략별 FSM만을 관리하며, 그래프나 큐, 월드 상태의 단일 소스는 아니다. Diff 이후 생성되는 토픽과 그 생명주기는 DAG Manager가 소유하고, 월드 정책과 활성 상태는 WorldService가 책임진다.
- **Commit Log** — 모든 전략 제출은 처리 전에 `gateway.ingest` 토픽(Redpanda/Kafka)에 append된다. Gateway는 오프셋을 Redis에 저장해 재시도 시점을 복원하며, DAG Manager와 WorldService가 발행하는 ControlBus 이벤트를 구독해 SDK로 중계한다. 이러한 로그 기반 경계는 장애 시 재생(replay)과 감사를 가능하게 한다.

---

## S6 · Worlds Proxy & Event Stream (New)

Gateway remains the single public boundary for SDKs. It proxies WorldService endpoints and provides an opaque event stream descriptor to SDKs; it does not compute world policy itself.

### Worlds Proxy

- Proxied endpoints → WorldService:
  - ``GET /worlds/{id}/decide`` → DecisionEnvelope (cached with TTL/etag)
  - ``GET /worlds/{id}/activation`` → ActivationEnvelope (fail‑safe: inactive on stale)
  - ``POST /worlds/{id}/evaluate`` / ``POST /worlds/{id}/apply`` (operator‑only)
- Caching & TTLs:
  - Per‑world decision cache honors envelope TTL (default 300s if unspecified); stale decisions → safe fallback (compute‑only, orders gated OFF)
  - Activation cache: stale/unknown → orders gated OFF; ActivationEnvelope MAY include `state_hash` for quick divergence checks
- Circuit breakers & budgets: Gateway periodically polls WorldService and DAG Manager status to drive circuit breakers.
- `/status` exposes circuit breaker states for dependencies, including WorldService.

- Strategy submission and worlds:
  - Clients may include `world_id` (single) **or** `world_ids[]` (multiple). Gateway upserts a **WorldStrategyBinding (WSB)** for each world and ensures the corresponding `WorldNodeRef(root)` exists in the WVG. Execution mode is still determined solely by WorldService decisions.
  - Gateway maps `DecisionEnvelope.effective_mode` to an ExecutionDomain for compute/context and writes it to envelopes it relays: `validate → backtest (orders gated OFF by default)`, `compute-only → backtest`, `paper → dryrun`, `live → live`. `shadow` is reserved and must be explicitly requested by operators.
  - Gateway forwards the compute context `{ world_id, execution_domain, as_of (if backtest), partition }` with diff/ingest requests so DAG Manager derives a Domain‑Scoped ComputeKey and isolates caches per domain.
  - Backtest/dryrun submissions MUST include `as_of` (dataset commit) and MAY include `dataset_fingerprint`; when absent Gateway rejects or falls back to compute-only mode to avoid mixing datasets.

### Event Stream Descriptor

SDKs obtain an opaque WebSocket descriptor from Gateway and subscribe to real‑time control updates without learning about ControlBus.

```
POST /events/subscribe
{ "world_id": "crypto_mom_1h", "strategy_id": "...", "topics": ["activation", "queues"] }
→ { "stream_url": "wss://gateway/ws/evt?ticket=...", "token": "<jwt>", "topics": ["activation"], "expires_at": "..." }
```

- Gateway subscribes to internal ControlBus and relays events to SDK over the descriptor URL.
- Ordering is guaranteed per key (world_id or tags+interval). Consumers deduplicate via ``etag``/``run_id``. First message per topic SHOULD be a full snapshot or carry a `state_hash`.

Token (JWT) claims (delegated WS or future use):
- `aud`: `controlbus`
- `sub`: user/service identity
- `world_id`, `strategy_id`, `topics`: subscription scope
- `jti`, `iat`, `exp`: idempotency and keying. Key ID (`kid`) is conveyed in the JWT header.

Token refresh
- Clients may refresh an expiring token on the same connection by sending `{ "type": "refresh", "token": "<jwt>" }`.
- On success Gateway updates scopes/topics in-place and returns `{ "type": "refresh_ack" }`.
- Failures emit `ws_refresh_failed` and close the socket with policy code 1008.

### Degrade & Fail‑Safe Policy (Summary)

- WorldService unavailable:
  - ``/decide`` → cached DecisionEnvelope if fresh; else safe default (compute‑only)
  - ``/activation`` → inactive
- Event stream unavailable:
  - Reconnect with provided ``fallback_url``; SDK may periodically reconcile via HTTP
- Live guard: Gateway rejects live trading unless consent is given.
  - When enabled, callers must include header ``X-Allow-Live: true``.
  - Starting Gateway with ``--allow-live`` disables the guard for testing.
- 2‑Phase apply handshake: during `Freeze/Drain`, Gateway MUST gate all order publications (OrderPublishNode outputs are suppressed). Gateway unblocks only after an `ActivationUpdated` event reflecting `freeze=false` post‑switch.
- Identity propagation: Gateway forwards caller identity (JWT subject/claims) to WorldService; WorldService logs it in audit records.

See also: World API Reference (reference/api_world.md) and Schemas (reference/schemas.md).

{{ nav_links() }}
- Status (2025-09):
  - Partition key is defined in `qmtl/dagmanager/kafka_admin.py:partition_key(node_id, interval, bucket)` and used by the commit‑log writer.
  - Transactional commit‑log writer/consumer are implemented (`qmtl/gateway/commit_log.py`, `qmtl/gateway/commit_log_consumer.py`) with deduplication and metrics.
  - OwnershipManager coordinates Kafka ownership with Postgres advisory locks fallback (`qmtl/gateway/ownership.py`), and `owner_reassign_total` is recorded on handoff.
  - SDK/Gateway integration skips local execution when queues are globally owned (see `qmtl/gateway/worker.py`).
  - Chaos/soak style dedup tests exist under `tests/gateway/test_commit_log_soak.py`.
