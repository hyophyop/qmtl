---
title: "QMTL Gateway — 제어면 인입과 프록시 경계"
tags: []
author: "QMTL Team"
last_modified: 2026-04-03
spec_version: v1.2
---

{{ nav_links() }}

# QMTL Gateway — 제어면 인입과 프록시 경계

## S0‑A. Core Loop 정렬 요약

- Gateway는 `/strategies` 제출을 받아 DAG Manager Diff/큐 매핑과 WorldService 프록시를 조합해 **compute_context `{world_id, execution_domain, as_of, partition}`**를 구성하고, Core Loop의 **단일 진입점 + 결정/큐 이벤트 브리지** 역할만 수행한다.
- ExecutionDomain/ComputeKey/EvalKey 규범은 `architecture.md`·`worldservice.md`·본 문서에서 동일하게 서술되며, 제출 메타의 도메인 힌트보다 WS 결정을 항상 우선한다.
- WS의 Decision/Activation/Allocation 결과와 Gateway의 상태 캐시/스트림 중계가 Runner/CLI `SubmitResult` 및 운영자용 CLI(예: world status, allocations)와 동일한 표면(필드·에러·TTL 의미)으로 이어진다.

## 관련 문서
- [Architecture Overview](README.md)
- [QMTL Architecture](architecture.md)
- [Core Loop 계약](../contracts/core_loop.md)
- [월드 라이프사이클 계약](../contracts/world_lifecycle.md)
- [DAG Manager](dag-manager.md)
- [WorldService](worldservice.md)
- [ControlBus](controlbus.md)
- [Lean Brokerage Model](lean_brokerage_model.md)
- [QMTL 구현 추적성](implementation_traceability.md)
- [Gateway 런타임 및 배포 프로필](../operations/gateway_runtime.md)

추가 참고
- 운영 가이드: [리스크 관리](../operations/risk_management.md), [타이밍 컨트롤](../operations/timing_controls.md)
- 레퍼런스: [Brokerage API](../reference/api/brokerage.md), [Commit‑Log 설계](../reference/commit_log.md), [World/Activation API](../reference/api_world.md)

!!! note "런타임과 배포"
    dev/prod 프로필, 기동 전 검증, 장애 대응 포인트는 [Gateway 런타임 및 배포 프로필](../operations/gateway_runtime.md)에서 운영 규칙으로 관리한다.

!!! note "Risk Signal Hub 연동"
- Gateway는 post-rebalance/fill 포트폴리오 스냅샷을 허브에 push 하는 producer 역할만 수행한다.
- Hub 저장소, 토큰, offload, freshness 운영은 [Risk Signal Hub 운영 런북](../operations/risk_signal_hub_runbook.md)에서 다룬다.

---

## S0 · 시스템 컨텍스트와 목표

Gateway는 일시적인 전략 제출과 DAG Manager가 관리하는 영속적 그래프 상태 사이의 **운영 경계**에 위치합니다. 설계 목표는 다음과 같습니다:

| ID     | Goal                                                         | Metric                    |
| ------ | ------------------------------------------------------------ | ------------------------- |
|  G‑01  | Diff submission queuing **loss‑free** under 1 k req/s burst  | `lost_requests_total = 0` |
|  G‑02  | **≤ 150 ms** p95 end‑to‑end latency (SDK POST → Warm‑up ack) | `gateway_e2e_latency_p95` |
|  G‑03  | 동시 제출 간 Kafka 토픽 중복 0                              | 불변 조건 §S3             |
|  G‑04  | 상태 업데이트 WebSocket 선형 전송(≥ 500 msg/s)              | WS 부하 테스트            |

**Ax‑1** SDK 노드는 정규 해싱 규칙을 준수합니다(Architecture §1.1 참조).
**Ax‑2** Neo4j causal 클러스터는 단일 리더 일관성을 노출하며, 리드 리플리카는 지연될 수 있습니다.
**Ax‑3** Gateway는 `{ world_id, execution_domain, as_of, partition }` 컴퓨트 컨텍스트를 구성해 하위 서비스로 전달합니다. SDK는 이 컨텍스트를 선택하지 않으며, Gateway가 WorldService 결정(및 필요 시 제출 메타데이터)에서 도출합니다. DAG Manager는 이를 통해 도메인 스코프 ComputeKey를 파생하고, WorldService는 정책 권한/적용에 사용합니다. 이 계약의 정식 구현은 `qmtl/foundation/common/compute_context.py`에 있으며, 커밋 로그 직렬화/다운그레이드 추적/인제스트 흐름용 Redis 매핑을 담당하는 `StrategyComputeContext`(`qmtl/services/gateway/submission/context_service.py`)로 래핑됩니다.

**경계 규칙:** Gateway는 submit 표면을 가능한 한 단순하게 유지하되, 실제 컨텍스트 구성과 제어면 오케스트레이션은 내부 서비스 조합으로 흡수해야 합니다. 공개 표면 변경이 필요할 때는 먼저 기존 계약([Core Loop 계약](../contracts/core_loop.md), [마이그레이션 가이드](../guides/migration_bc_removal.md)) 안에서 해결 가능한지 검토합니다.

### 비목표
- Gateway는 월드 정책 결정을 계산하지 않으며, 월드/큐의 SSOT가 아닙니다.
- Gateway는 브로커리지 실행을 관리하지 않고, 요청 중재와 제어 이벤트 중계만 담당합니다.

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

참고: 간결성을 위해 이 분해도에서 WorldService와 ControlBus는 생략했습니다. 월드 프록시와 불투명 이벤트 스트림 인계는 §S6을 참고하세요. 전체 시스템에서는 Gateway가 ControlBus를 구독하고 WorldService API를 프록시합니다.

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

!!! note "추가 엔드포인트"
    아래 OpenAPI 발췌는 핵심 경로만 포함합니다. 전체 라우트 인벤토리와 현재 공개 범위는 레퍼런스 문서와 구현(`qmtl/services/gateway/routes/**`)을 기준으로 관리합니다.

    - 전략: ``POST /strategies/dry-run`` , ``POST /strategies/{strategy_id}/history``
    - 이벤트/스키마: ``GET /events/jwks`` , ``GET /events/schema`` (WebSocket 구독은 별도)
    - 인제스트: ``POST /fills`` (인제스트 엔드포인트 구현됨)
    - 관측성: ``GET /metrics``
    - 리밸런싱: ``POST /rebalancing/execute`` (및 WorldService 프록시 ``/rebalancing/plan``)

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
  "world_ids": ["crypto_mom_1h", "crypto_alt_1h"]
}
```

> **Backtests & dry-runs:** When `meta.execution_domain` resolves to `backtest` or
> `dryrun` (including aliases such as `compute-only`, `paper`, or `sim`), callers
> MUST include `meta.as_of`. Gateway downgrades missing values to compute-only
> backtests, enters safe mode, and records the event via
> `strategy_compute_context_downgrade_total{reason="missing_as_of"}`. The
> downgrade reasons are defined by the shared `DowngradeReason` enum in
> `qmtl/foundation/common/compute_context.py` to keep replay and commit-log behavior in
> sync. When WorldService is unreachable the submission also enters safe mode
> with downgrade reason `decision_unavailable`, ensuring live domains cannot
> execute without an authoritative decision envelope.

`meta.execution_domain`는 호출자 힌트일 뿐 최종 도메인은 WorldService의 `effective_mode`
결과를 Gateway가 정규화한 값입니다. 별칭 매핑은 `compute-only/validate → backtest`,
`paper/sim → dryrun`, `live → live`, `shadow`(운영자 전용)이며, WS 결정이 없거나 오래된
상태에서 `live` 요청은 compute-only(backtest)로 강등됩니다.

**POST /strategies — HTTP Status**

| HTTP Status         | Meaning                                 | Typical Cause      |
| ------------------- | --------------------------------------- | ------------------ |
|  202 Accepted       |  Ingest successful, StrategyID returned | Nominal            |
|  400 Bad Request   |  Submission rejected                     | NodeID validation failure (`E_CHECKSUM_MISMATCH`, `E_NODE_ID_FIELDS`, `E_NODE_ID_MISMATCH`) |
|  409 Conflict       |  Duplicate StrategyID within TTL        | Same DAG re‑submit (`E_DUPLICATE`) |
|  422 Unprocessable  |  Schema validation failure              | `StrategySubmit` payload invalid (FastAPI/Pydantic 422) |

**Example Queue Lookup**

```http
GET /queues/by_tag?tags=t1,t2&interval=60&match_mode=any HTTP/1.1
Authorization: Bearer <jwt>
```

| HTTP Status         | Meaning                          | Typical Cause      |
| ------------------- | -------------------------------- | ------------------ |
|  200 OK             |  Queue lookup successful         | Nominal            |
|  422 Unprocessable  |  Query parameter validation fail | Missing/invalid `tags` or `interval` |

---

## S3 · Exactly‑Once Execution (Node×Interval×Bucket)

This section summarizes the once‑and‑only‑once layer required by issue #544.

- Ownership: For each execution key `(node_id, interval, bucket_ts)`, a single worker acquires ownership before executing. Gateway uses a DB advisory lock (Postgres `pg_try_advisory_lock`) with optional Kafka‑based coordination driven by `gateway.ownership.mode`, `gateway.ownership.bootstrap`, `gateway.ownership.topic`, `gateway.ownership.group_id` (plus retry/backoff knobs). The Kafka path grants ownership when the worker's consumer group owns the partition for the key and falls back to Postgres when unavailable.
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
- Gateway는 `node_type`, `code_hash`, `config_hash`, `schema_hash`, `schema_compat_id`가 빠진 제출을 `E_NODE_ID_FIELDS`로 거부하며, 제공된 `node_id`가 정규 `compute_node_id()` 출력과 다를 경우 `E_NODE_ID_MISMATCH`를 반환합니다. `node_ids_crc32`(CRC32) 불일치의 경우 `E_CHECKSUM_MISMATCH`를 반환합니다. 또한 `schema_compat_id`와 레거시 `schema_id`가 동시에 존재하고 값이 다르면 `E_SCHEMA_COMPAT_MISMATCH`로 거부합니다. 모든 오류에는 SDK 클라이언트가 BLAKE3 계약에 따라 DAG를 재생성할 수 있도록 실행 가능한 힌트를 포함합니다.

인제스트 직후, Gateway는 전략 코드 변경 없이 롤백과 카나리아 트래픽 제어를 조율할 수 있도록 DAG에 `VersionSentinel` 노드를 삽입합니다. 운영 환경에서의 on/off 정책과 설정 표면은 [Gateway 런타임 및 배포 프로필](../operations/gateway_runtime.md)에서 다룹니다.

!!! note "Design intent"
- TagQuery canonicalization keeps `NodeID` stable; dynamic queue discovery is a runtime concern (ControlBus → SDK TagQueryManager), not part of canonical hashing.
- Execution domains are derived centrally by Gateway from WorldService decisions (see §S0) and propagated via the shared `ComputeContext`; SDK treats the result as input only.
- VersionSentinel is default-on to enable rollout/rollback/traffic-split without strategy changes; disable only in low‑risk, low‑frequency environments.

Gateway는 FSM을 Redis 및 데이터베이스(이벤트 로그)로 기록합니다. Redis AOF/데이터베이스 WAL 등 내구성 보장은 애플리케이션 로직이 아니라 **배포/인프라 설정**으로 강제되어야 합니다. 이는 아키텍처(§2)에서 설명한 Redis 장애 시나리오를 완화합니다.

When resolving `TagQueryNode` dependencies, the Runner's **TagQueryManager**
invokes ``resolve_tags()`` which issues a ``/queues/by_tag`` request. Gateway
consults DAG Manager for queues matching `(tags, interval)` and returns the list
so that TagQueryNode instances remain network‑agnostic and only nodes lacking
upstream queues execute locally.

Gateway also listens (via ControlBus) for `sentinel_weight` CloudEvents emitted by DAG Manager. Upon receiving an update, Gateway updates local metrics and broadcasts the new weight to SDK clients via WebSocket. The effective ratio per sentinel is exported as the Prometheus gauge `gateway_sentinel_traffic_ratio{sentinel_id="<id>"}`.

WorldService에서 발행하는 `rebalancing_planned` ControlBus 이벤트 역시 Gateway가 중복을 제거한 뒤 WebSocket `rebalancing` 토픽(CloudEvent 타입 `rebalancing.planned`)으로 중계하며, 계획 건수와 자동 실행 시도를 나타내는 지표(`rebalance_plans_observed_total`, `rebalance_plan_last_delta_count`, `rebalance_plan_execution_attempts_total`, `rebalance_plan_execution_failures_total`)를 기록한다.

### S5 · Reliability Checklist

* **NodeID CRC 파이프라인** – SDK가 전송한 `node_id`와 Gateway가 재계산한 값이
  diff 요청 및 응답의 `crc32` 필드로 상호 검증된다. CRC 불일치가 발생하면 HTTP 400으로 반환된다.
* **TagQueryNode 런타임 확장** – Gateway가 새 `(tags, interval)` 큐를 발견하면
  `tagquery.upsert` CloudEvent를 발행하고 Runner의 **TagQueryManager**가 이를
  수신해 노드 버퍼를 자동 초기화한다.
* **Local DAG Fallback Queue** – DAG Manager가 응답하지 않을 때 제출된 전략 ID는
  메모리에 임시 저장되며 서비스가 복구되면 Redis 큐로 플러시된다.
* **Sentinel weight 적용 지연** – `traffic_weight` 변경 후 Gateway가 해당 ratio를 로컬 메트릭에 반영하기까지의 지연을 `sentinel_skew_seconds` 지표로 측정한다.

### 운영 표면

Gateway의 기동 커맨드, 구성 파일, `qmtl config validate` 절차, 테스트용 라이브 가드 override는 [Gateway 런타임 및 배포 프로필](../operations/gateway_runtime.md)과 [Config CLI](../operations/config-cli.md)에서 운영 규칙으로 관리한다.

---

## S4 · Ownership & Commit‑Log Design

- **Ownership** — Gateway는 제출 요청 큐(FIFO)와 전략별 FSM만을 관리하며, 그래프나 큐, 월드 상태의 단일 소스는 아니다. Diff 이후 생성되는 토픽과 그 생명주기는 DAG Manager가 소유하고, 월드 정책과 활성 상태는 WorldService가 책임진다.
- **Commit Log** — 모든 전략 제출은 처리 전에 `gateway.ingest` 토픽(Redpanda/Kafka)에 append된다. Gateway의 commit-log 컨슈머는 Kafka consumer group offset commit을 사용하며(처리 성공 후 커밋), 중복 제거 및 메트릭을 제공한다. DAG Manager와 WorldService가 발행하는 ControlBus 이벤트를 구독해 SDK로 중계한다. 이러한 로그 기반 경계는 장애 시 재생(replay)과 감사를 가능하게 한다.

---

## S6 · Worlds Proxy & Event Stream (New)

Gateway remains the single public boundary for SDKs. It proxies WorldService endpoints and provides an opaque event stream descriptor to SDKs; it does not compute world policy itself.

### Worlds Proxy

- Proxied endpoints → WorldService:
  - ``GET /worlds/{id}/decide`` → DecisionEnvelope (cached with TTL/etag)
  - ``GET /worlds/{id}/activation`` → ActivationEnvelope (fail‑safe: inactive on stale)
  - ``GET /worlds/{id}/activation/state_hash`` → activation state hash metadata
  - ``POST /worlds/{id}/evaluate`` / ``POST /worlds/{id}/apply`` (operator‑only)
- Caching & TTLs:
  - Per‑world decision cache honors envelope TTL (default 300s if unspecified); stale decisions → safe fallback (compute‑only, orders gated OFF)
  - Activation cache: stale/unknown → orders gated OFF; divergence 확인은 ``GET /worlds/{id}/activation/state_hash``와 activation 이벤트를 사용합니다(ActivationEnvelope 필드가 아님)
- Circuit breakers & budgets: Gateway periodically polls WorldService and DAG Manager status to drive circuit breakers.
- `/status` exposes circuit breaker states for dependencies, including WorldService.

- 전략 제출과 월드:
  - 클라이언트는 `world_ids[]`(다중)를 보내야 합니다. 레거시 단일 필드 `world_id`는 전이 입력으로만 허용되며 `world_ids=[world_id]`로 정규화됩니다. 세부 마이그레이션은 [마이그레이션: 레거시 모드 및 하위 호환성 제거](../guides/migration_bc_removal.md)를 따릅니다. Gateway는 각 월드에 대해 **WorldStrategyBinding(WSB)**을 upsert하고, WVG에서 해당 `WorldNodeRef(root)`가 존재하도록 보장합니다. 실행 모드는 여전히 WorldService 결정만으로 정해집니다.
  - `gateway.worldservice_url`이 설정되어 있거나 `WorldServiceClient`가 주입된 경우, 제출 헬퍼는 `POST /worlds/{world_id}/bindings`로 각 바인딩을 WorldService에 미러링합니다. 중복 바인딩은 HTTP 409를 반환하며 성공으로 간주합니다. 일시 오류는 로깅되지만 인제스트를 차단하지 않습니다.
  - Gateway는 `DecisionEnvelope.effective_mode`를 ExecutionDomain으로 매핑해 중계하는 봉투에 기록합니다: `validate → backtest(주문 게이트 기본 OFF)`, `compute-only → backtest`, `paper/sim → dryrun`, `live → live`. 동일 매핑은 프록시된 ActivationEnvelope에도 적용되어, WorldService가 필드를 생략하더라도 클라이언트가 명시적 `execution_domain`을 받도록 합니다. `shadow`는 예약된 값으로 운영자가 명시적으로 요청해야 합니다. SDK/Runner는 이 매핑을 입력으로만 취급합니다.
  - Gateway는 diff/ingest 요청과 함께 `{ world_id, execution_domain, as_of(백테스트 시), partition }` 컴퓨트 컨텍스트를 전달하여 DAG Manager가 도메인 스코프 ComputeKey를 파생하고 캐시를 도메인별로 격리하도록 합니다. 호출자가 백테스트 메타데이터를 제공하지 않으면, Gateway는 WS에서 컨텍스트를 도출하거나 선택 필드를 생략합니다. DAG Manager는 안전한 기본값과 컨텍스트 스코프 격리를 적용합니다.
  - 백테스트/드라이런 제출은 `as_of`(데이터셋 커밋)를 반드시 포함해야 하며, `dataset_fingerprint`를 포함할 수 있습니다. 누락 시 Gateway는 요청을 거부하거나 데이터셋 혼합을 피하기 위해 compute‑only 모드로 강등합니다.

### 이벤트 스트림 디스크립터(Event Stream Descriptor)

SDK는 Gateway로부터 불투명(opaque) WebSocket 디스크립터를 받아 ControlBus 세부를 알지 못한 채 실시간 제어 업데이트를 구독합니다.

```
POST /events/subscribe
{ "world_id": "crypto_mom_1h", "strategy_id": "...", "topics": ["activation", "queues"] }
→ { "stream_url": "wss://gateway/ws/evt?ticket=...", "token": "<jwt>", "topics": ["activation"], "expires_at": "..." }
```

- Gateway는 내부 ControlBus를 구독하고 디스크립터 URL을 통해 SDK로 이벤트를 중계합니다.
- 순서는 키(월드 또는 태그+인터벌) 단위로 보장됩니다. 컨슈머는 ``etag``/``run_id``로 중복 제거합니다. 각 토픽의 첫 메시지는 전체 스냅샷이어야 하며, activation 토픽은 divergence 확인을 위해 activation 이벤트에 `state_hash`를 포함하는 것이 바람직합니다.
- **공개 범위:** 이 디스크립터는 현재 ActivationManager, TagQueryManager 등 SDK 내부용입니다. 사용자 대상의 범용
  CLI/SDK 구독 헬퍼는 아직 없으므로, 안정화된 표면이 제공될 때까지 `qmtl status`, `GET /worlds/{id}` 같은
  Gateway/WorldService 엔드포인트를 폴링하세요.

토큰(JWT) 클레임(위임 WS 또는 향후 용도):
- `aud`: `controlbus`
- `sub`: user/service identity
- `world_id`, `strategy_id`, `topics`: subscription scope
- `jti`, `iat`, `exp`: idempotency and keying. Key ID (`kid`) is conveyed in the JWT header.

토큰 갱신
- 클라이언트는 동일 연결에서 `{ "type": "refresh", "token": "<jwt>" }`를 보내 만료 임박 토큰을 갱신할 수 있습니다.
- 성공 시 Gateway는 스코프/토픽을 제자리에서 업데이트하고 `{ "type": "refresh_ack" }`을 반환합니다.
- 실패 시 `ws_refresh_failed` 이벤트를 내보내고 정책 코드 1008로 소켓을 종료합니다.

### 강등 및 페일세이프 정책(요약)

- WorldService 비가용:
  - ``/decide`` → 캐시된 DecisionEnvelope이 신선하면 사용, 아니면 안전 기본값(compute‑only)
  - ``/activation`` → 비활성
- 이벤트 스트림 비가용:
  - 제공된 ``fallback_url``로 재연결; SDK는 주기적으로 HTTP 동기화를 수행할 수 있습니다.
- 라이브 가드: 명시적 동의 없이는 라이브 거래를 거부합니다.
  - 활성화 시 호출자는 헤더 ``X-Allow-Live: true``를 포함해야 합니다.
  - 테스트용 override 표면은 [Gateway 런타임 및 배포 프로필](../operations/gateway_runtime.md)에서 관리합니다.
- 2‑단계 Apply 핸드셰이크: `Freeze/Drain` 동안 Gateway는 모든 주문 발행을 차단해야 합니다(OrderPublishNode 출력 억제). 스위치 후 `freeze=false`가 반영된 `ActivationUpdated` 이벤트를 수신한 뒤에만 차단을 해제합니다.
- 아이덴티티 전파: Gateway는 호출자 아이덴티티(JWT subject/claims)를 WorldService로 전달하고, WorldService는 감사 로그에 기록합니다.

참고: World API 레퍼런스(reference/api_world.md) 및 스키마(reference/schemas.md).

구현 범위와 현재 모듈 분해, 테스트 자산은 [QMTL 구현 추적성](implementation_traceability.md)과 Gateway 런타임 문서에서 계속 추적합니다.

{{ nav_links() }}
