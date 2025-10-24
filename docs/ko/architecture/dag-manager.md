---
title: "QMTL DAG Manager — 상세 설계서 (Extended Edition)"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
spec_version: v1.1
---

{{ nav_links() }}

# QMTL DAG Manager — 상세 설계서 (Extended Edition)

> **Revision 2025‑06‑04 / v1.1**  — 문서 분량 +75% 확장, 실전 운영 기준 세부 스펙 포함

## 관련 문서
- [Architecture Overview](README.md)
- [QMTL Architecture](architecture.md)
- [Gateway](gateway.md)
- [Lean Brokerage Model](lean_brokerage_model.md)

추가 참고
- 레퍼런스: [Commit‑Log 설계](../reference/commit_log.md), [TagQuery 사양](../reference/tagquery.md)
- 운영 가이드: [타이밍 컨트롤](../operations/timing_controls.md)

---

## 0. 역할 요약 & 설계 철학

| 핵심 책임                               | 세부 설명                                                | 관련 섹션        |
| ----------------------------------- | ---------------------------------------------------- | ------------ |
| **Graph DB Single Source of Truth** | Neo4j Property Graph → 모든 전략 노드·토픽·버전 메타가 단일 그래프에 영속 | §1 데이터 모델    |
| **DAG Diff 엔진**                     | 제출 DAG와 Neo4j 그래프 간 구조·해시 비교 → 재사용/신규 노드 판정·토픽 매핑     | §2 Diff 알고리즘 |
| **토픽 오케스트레이션**                       | Idempotent 토픽 생성·TTL·GC·버전 롤아웃, ref‑count 기반 제거      | §3, §4       |
| **버전 관리·롤백**                        | Version Sentinel 노드로 그래프 버전 경계 표시 → 카나리아 트래픽 스플릿·롤백  | §2, §3‑A     |
| **SRE Friendly**                    | gRPC/HTTP 인터페이스, 메트릭·로그·Alert 통합, Admin CLI          | §6, §10      |

> **설계 철학:** “계산 그래프 + 메시징 큐”를 **불변 ID**로 연결해 재현성·롤백 가능성을 최우선. 모든 변형은 새 노드·토픽으로 분기하고, 레거시는 TTL+GC로 안전 제거.
> SDK 측에서 실행되는 모든 `compute_fn`은 `NodeCache.view()`가 반환하는 read-only `CacheView` 한 개만을 인자로 받는다.

---

## 0-A. Ownership & Commit-Log Design

- **Ownership** — DAG Manager는 ComputeNode와 Queue 메타데이터의 단일 소스로서 토픽 생성·버전 롤아웃·GC를 전담한다. Gateway는 제출 파이프라인을 조정하지만 그래프 상태를 소유하지 않으며, WorldService는 월드·결정 상태를 유지한다.
- **Commit Log** — 모든 큐는 Redpanda/Kafka의 append-only 토픽으로 구현되며, DAG Manager는 `QueueUpdated` 등 제어 이벤트를 ControlBus 토픽에 발행한다. 토픽 생성·삭제 이력도 관리 로그에 기록되어 장애 시점 복원과 감사(audit)을 지원한다.

> Terminology / SSOT boundary: Global Strategy Graph(GSG, 전역 DAG)의 SSOT는 DAG Manager이며 불변(append‑only)이다. 월드‑로컬 객체(World View Graph=WVG: WorldNodeRef, Validation, DecisionsRequest)는 WorldService의 SSOT이며 DAG Manager는 저장하지 않는다(읽기/쓰기 금지). 용어 정의는 Architecture Glossary(architecture/glossary.md) 참고.

### 0-A.1 커밋 로그 메시지 키와 파티셔닝

- 파티션 키는 `partition_key(node_id, interval, bucket_ts)`에서 파생되며, Gateway가 사용하는 전체 Kafka 메시지 키는 다음과 같습니다:

  `"{partition_key(node_id, interval, bucket_ts)}:{input_window_hash}"`

  동일 실행 키에 대해 모든 입력 윈도우를 가로지르는 로그 컴팩션을 허용하면서, 윈도우별 고유성을 유지합니다.

- 컨슈머는 `(node_id, bucket_ts, input_window_hash)` 삼중 항목으로 중복을 제거해야 합니다.


---

## 1. 데이터 모델 (Neo4j Property Graph)

### 1.1 노드·관계 스키마

| Label             | 필수 속성                                                           | 선택 속성                                   | 설명                      |
| ----------------- | --------------------------------------------------------------- | --------------------------------------- | ----------------------- |
| `ComputeNode`     | `node_id`(pk), `node_type`, `interval`, `period`, `code_hash`, `schema_compat_id`, `params_canon` | `created_at`, `tags[]`, `owner`, `schema_hash`         | DAG 연산 노드 (지표·전처리·매매 등) |
| `Queue`           | `topic`, `created_at`, `ttl`, `retention_ms`                    | `brokers`, `tag`, `lag_alert_threshold` | Kafka/Redpanda 토픽       |
| `VersionSentinel` | `version`, `commit_hash`, `created_at`                          | `release_tag`, `traffic_weight`         | 버전 경계 · 롤백 포인트          |
| `Artifact`        | `path`, `checksum`, `size`                                      | `framework`, `dtype`                    | 모델·파라미터 파일 등 binary     |

**Relationships**

```
(ComputeNode)-[:EMITS]->(Queue)
(VersionSentinel)-[:HAS]->(ComputeNode)
(Artifact)-[:USED_BY]->(ComputeNode)
```

### 1.2 인덱스 & 제약 조건

아래 제약/인덱스는 초기화시 항상 idempotent(재실행 안전)하도록 `IF NOT EXISTS`를 사용합니다. 운영 환경에서 재배포/재시작 시에도 스키마 초기화 커맨드를 반복 호출할 수 있습니다.

```cypher
// 기본 제약/인덱스
CREATE CONSTRAINT compute_pk IF NOT EXISTS ON (c:ComputeNode) ASSERT c.node_id IS UNIQUE;
CREATE INDEX kafka_topic IF NOT EXISTS FOR (q:Queue) ON (q.topic);

// 성능 최적화 인덱스 (태그 조회, 주기 필터, 버퍼 스캔)
CREATE INDEX compute_tags IF NOT EXISTS FOR (c:ComputeNode) ON (c.tags);
CREATE INDEX queue_interval IF NOT EXISTS FOR (q:Queue) ON (q.interval);
CREATE INDEX compute_buffering_since IF NOT EXISTS FOR (c:ComputeNode) ON (c.buffering_since);
```

CLI 사용법:

```
# 스키마 초기화 (idempotent)
qmtl service dagmanager neo4j-init --uri bolt://localhost:7687 --user neo4j --password neo4j

# 현재 스키마 내보내기
qmtl service dagmanager export-schema --uri bolt://localhost:7687 --user neo4j --password neo4j --out schema.cypher
```
### 1.3 NodeID 생성 규칙
- NodeID = `blake3:<digest>`이며, 다음의 정규 직렬화 입력을 해시합니다: 
  `(node_type, interval, period, params(분리·정규화), dependencies(node_id 기준 정렬), schema_compat_id, code_hash)`
- 비결정적 필드(타임스탬프, RNG 시드, 환경변수)는 입력에서 제외합니다. 분리 가능한 파라미터는 개별 필드로 나누고, 키 정렬·숫자 정밀도 고정의 정규 JSON으로 직렬화합니다.
- NodeID에는 `world_id`가 포함되면 안 됩니다. 월드 격리는 WVG(World View Graph)와 큐 네임스페이스(예: world `topic_prefix`)의 책임입니다.
- 정규화 보장:
  - 내용이 동일한 파라미터 맵은(삽입/키 순서 무관) 동일한 NodeID로 해시됩니다.
  - 의존성 식별자는 해시 전 사전식으로 정렬하여 업로드 순서가 다이제스트에 영향을 주지 않도록 합니다.
  - 표시용 메타데이터(`name`, `tags`, `metadata` 등)와 비결정적 입력은 해시 전에 제거합니다.
  - `blake3:` 접두사가 없는 NodeID는 Gateway 검증에서 거부됩니다.
  - 충돌 완화: `existing_ids`에 이미 동일 다이제스트가 있을 때 도메인 분리 접미사를 사용한 결정적 재해시(BLAKE3)를 적용합니다(§3.1의 XOF 권고 반영).
- TagQueryNode 정규화:
  - 런타임에 해석된 업스트림 큐 집합은 `dependencies`에 포함하지 않습니다.
  - 대신 질의 명세를 `params_canon`에 포함합니다(정규화된 `query_tags` 정렬, `match_mode`, `interval`).
  - 큐의 동적 발견/확장은 ControlBus 이벤트로 처리되며 NodeID에는 영향을 주지 않습니다.
- `schema_compat_id`를 사용합니다(`schema_hash`가 아님). 경미한 스키마 변경은 새 NodeID를 강제하지 않고 버퍼링되며, 호환 불가일 때만 새 ID가 생성됩니다.
- 표시 전용 메타데이터(표시 이름 `name`, 분류 태그 `tags`)는 NodeID에 포함되지 않습니다. 기능적 파라미터만 `params_canon`에 포함됩니다.
- Use BLAKE3; on collision-hardening use **BLAKE3 XOF** (longer output) with domain separation. All IDs must carry the `blake3:` prefix.
- Uniqueness enforced via `compute_pk` constraint. `schema_compat_id` references the Schema Registry’s major‑compat identifier for the node's message format.
- **Schema compatibility:** Minor/Patch 수준의 스키마 변경은 `schema_compat_id`를 유지하여 `node_id`를 보존한다. 실제 바이트 수준 스키마 변경은 선택 속성 `schema_hash`로 추적해 버퍼링/재계산 정책에 활용한다.

### 1.4 Domain‑Scoped ComputeKey (new)

- Rationale: NodeID is global and world‑agnostic by design. To prevent accidental cross‑world/domain reuse in caches and runtime de‑duplication, a separate ComputeKey is used for execution/caching.
- Definition:

  `ComputeKey = blake3(NodeHash ⊕ world_id ⊕ execution_domain ⊕ as_of ⊕ partition)`

  - `NodeHash` is the canonical hash used by NodeID (§1.3).
  - `world_id` scopes execution to a world; `execution_domain ∈ {backtest,dryrun,live,shadow}` ensures backtest/live separation.
  - `as_of` binds backtests to a dataset snapshot/commit; required for deterministic replay.
  - `partition` optionally scopes multi‑tenant or strategy/portfolio partitions.
- Usage:
  - NodeCache and any compute de‑duplication MUST key on `ComputeKey` (not solely on `node_id`).
  - Cross‑context cache hits (same `node_id`, different `(world_id|execution_domain|as_of|partition)`) MUST be treated as violations and reported via a metric `cross_context_cache_hit_total` and blocked by policy (SLO: 0).
  - Queue topics and NodeID remain unchanged; ComputeKey does not alter topic naming. Operators MAY additionally deploy namespace prefixes `{world_id}.{execution_domain}.<topic>` at the broker level for operational isolation (see WorldService doc).
  - Instrumentation: DAG Manager and SDK MUST emit `cross_context_cache_hit_total` and alert when >0 (critical). Promotion workflows must halt until cleared.
  - Completeness: `as_of` MUST be non-empty for backtests/dryruns; Gateway supplies the value. When missing, the shared `ComputeContext.evaluate_safe_mode()` helpers (see `qmtl/foundation/common/compute_context.py`) downgrade the request to the compute-only/backtest domain, flip the safe-mode flags, and block reuse without ever emitting a "live" sentinel.

Note: This design preserves NodeID stability while providing strong execution isolation across worlds and domains.

---

## 2. Diff 알고리즘 (v2)

### 2.1 입력·출력 정의

* **Input:** `DiffReq{strategy_id, dag_json, world_id?, execution_domain?, as_of?, partition?, dataset_fingerprint?}` (\~10‑500 KiB)
* **Output:** stream `DiffChunk{queue_map[], sentinel_id, version}`

### 2.2 단계별 상세 로직

1. **Node Pre‑scan** O(N) 

   * 파이썬 `orjson` → DAG dict → topo sort → node\_id list.
2. **DB Fetch** Batch `MATCH (c:ComputeNode WHERE c.node_id IN $list)` → 기존 노드 맵.
3. **Hash Compare**

   | 케이스                 | 처리               | 큐 정책                                             |
   | -------------------- | ---------------- | ------------------------------------------------ |
   | `node_id` 동일          | **재사용**          | 기존 Queue join                                    |
   | Back‑compat 스키마 변경    | **재사용 + 버퍼링 모드** | 큐 lag = history size, 7일 이후 자동 full‑recompute |
   | `node_id` 상이           | **신규 노드·큐**      | `topic_suffix=_v{n}`, TTL inherit                |
4. **Sentinel 삽입** `CREATE (:VersionSentinel{...})‑[:HAS]->(new_nodes)` (옵션)
5. **Queue Upsert**

   * Kafka Admin API must run with idempotent topic creation enabled as noted in the architecture (section 2).
   * gRPC Bulk `CreateTopicsRequest` idempotent.
   * 실패 시 `CREATE_TOPICS→VERIFY→WAIT→BACKOFF` 5단계 재시도를 수행하고,
     VERIFY 단계에서 broker metadata를 조회하여 유사 이름 충돌 여부를 확인한다.
6. **Stream 전송** 100 items/≤1 MiB chunk + ACK window(10).

### 2.3 알고리즘 복잡도

* 그래프 인덱스 hit → O(N) 
* Network Δ ≈ (#chunks × rtt)
* 1k 노드 기준 p95 < 80 ms (λ=50 req/s 시험 환경)

---

### 2‑A. Gateway ↔ DAG Manager Interface (확장)

| 방향  | Proto | Endpoint                      | Payload         | 응답                 | Retry/Timeout      | 목적               |
| --- | ----- | ----------------------------- | --------------- | ------------------ | ------------------ | ---------------- |
| G→D | gRPC  | `DiffService.DiffRequest`     | DAG             | `DiffChunk stream` | backoff 0.5→4 s ×5 | Diff & 토픽 매핑      |
| G→D | gRPC  | `AdminService.Cleanup`        | strategy\_id    | Ack                | 1 retry            | ref‑count decref |
| G→D | gRPC  | `AdminService.GetQueueStats`  | filter          | Stats              | 300 ms             | 모니터링             |
| G→D | gRPC  | `HealthCheck.Ping`            | –               | Pong               | 30 s interval      | Liveness         |
| G→D | HTTP  | `/admin/gc-trigger`           | id              | 202                | 2 retry            | Manual GC        |
| G→D | gRPC  | `AdminService.RedoDiff`       | sentinel\_id    | DiffResult         | manual             | 재Diff·롤백         |
| D→G | CB    | `queue` topic                 | queue_update/gc | at-least-once      | –                  | 큐 이벤트         |
|     |       |                               |                 |     |                    | 자세한 절차는 [Canary Rollout Guide](../operations/canary_rollout.md) 참조 |

### 2-B. Sentinel Traffic

Sentinel weight updates are published as `sentinel_weight` events on the ControlBus. See the [Canary Rollout Guide](../operations/canary_rollout.md) for details.

---

## 3. 토픽 생성 & 명명 규칙 (확장)

### 3.1 토픽 이름 컨벤션

```
{asset}_{node_type}_{short_hash}_{version}
```

* `short_hash = first 8 of node_id digest` → 충돌 시 길이+2.
* 기본 토픽 설정은 코드의 ``_TOPIC_CONFIG`` 에서 관리되며 ``get_config(topic_type)`` 으로 조회한다.
* `{version}` 값은 `VersionSentinel.version` 혹은 전략 메타데이터(`meta.version`, `meta.strategy_version`)에서 파생되며, 제공되지 않으면 `v1`로 디폴트된다.

### 3.2 QoS & 레플리카 설정

| 토픽 타입        | partitions | rep\_factor | retention | compaction |
| ----------- | ---------- | ----------- | --------- | ---------- |
| Raw (price) | 3          | 3           | 7d        | none       |
| Indicator   | 1          | 2           | 30d       | delete     |
| Trade Exec  | 1          | 3           | 90d       | none       |

---

### 3‑A. End‑to‑End Interaction Scenarios (확장)

*(이전 표 + `RedoDiff` & 카나리아 포함)*

| # | 시나리오                       | 요약                                                                                     |
| - | -------------------------- | -------------------------------------------------------------------------------------- |
| 5 | **RedoDiff for Hotfix**    | 버그 수정 코드 빠르게 패치 → `RedoDiff` gRPC 요청 → 새 토픽 vX.Y.Z‑hotfix 생성 후 스왑                       |

---

### 3‑B. Control Events (QueueUpdated) (New)

DAG Manager는 큐 가용성 및 태그 해상도에 대한 제어‑플레인 업데이트를 발행하여 Gateway가 폴링 없이 실시간으로 SDK를 갱신할 수 있게 합니다.

- 발행자: DAG Manager → ControlBus(내부)
- 이벤트: ``QueueUpdated`` 스키마

```json
{
  "type": "QueueUpdated",
  "tags": ["BTC", "price"],
  "interval": 60,
  "queues": ["q1", "q2"],
  "etag": "q:BTC.price:60:77",
  "ts": "2025-08-28T09:00:00Z"
}
```

의미론(Semantics)
- 파티션 키: ``hash(tags, interval)``; 파티션 내부에서만 순서 보장
- 최소 1회 전달; 컨슈머는 ``etag``로 중복 제거
- Gateway는 구독 후 WS로 SDK에 재브로드캐스트; 분기 시 SDK TagQueryManager가 주기적 HTTP 리컨실로 복구

```mermaid
sequenceDiagram
    participant G as Gateway
    participant D as DAG Manager
    Note over G,D: Canary traffic 10% → 50%
        D-->>G: 202 OK
```

---

참고: 큐/태그 변경, 트래픽 가중치 등 제어 업데이트는 내부 ControlBus에 게시되며, Gateway가 WebSocket으로 SDK에 중계합니다. 별도의 콜백 인터페이스는 제공하지 않습니다.

## 4. Garbage Collection (Orphan Queue GC) (확장)

* **정책 매트릭스:**

  | Queue Tag   | TTL  | Grace Period | GC Action  |
  | ----------- | ---- | ------------ | ---------- |
| `raw`       | 7d   | 1d           | 삭제       |
| `indicator` | 30d  | 3d           | 삭제       |
| `sentinel`  | 180d | 30d          | S3 보관    |

* **보관 구현:** 삭제 전에 `S3ArchiveClient`로 센티널 큐를 S3에 업로드합니다.

* **동적 레이트 리미터:** Prometheus `kafka_server_BrokerTopicMetrics_MessagesInPerSec`가 80%를 넘으면 GC 배치 크기를 절반으로 줄입니다.

---

## 5. 장애 시나리오 & 복구 (확장)

| 장애                    | 영향              | 탐지 메트릭                        | 복구 절차                                  | 알림         |
| --------------------- | --------------- | ----------------------------- | -------------------------------------- | ---------- |
| Neo4j 리더 다운       | Diff 거절         | `raft_leader_is_null`         | 자동 리더 선출                           | PagerDuty |
| Kafka ZK 세션 손실    | 토픽 생성 실패        | `kafka_zookeeper_disconnects` | 지수형 재시도, 관리자 노드 폴백              | Slack #ops |
| Diff 스트림 정체      | 게이트웨이 상태 폴링 실패 | `ack_status=timeout`          | 마지막 ACK 오프셋부터 재개                 | Opsgenie  |
---

각 행은 Runbook 마크다운 파일과 대응되는 ID를 가지며, Grafana Dashboard URL과
교차 링크된다. 이를 통해 "재현 가능 사고 대응" 절차를 문서화한다.

## 6. 관측 & 메트릭 (확장)

| 메트릭                     | 목표   | 알림 규칙                 |
| -------------------------- | ------ | ------------------------ |
| `diff_duration_ms_p95`     | <80 ms | `>200ms 5분 지속 → 경고` |
| `queue_create_error_total` | =0     | `15분 내 >0 → 치명`      |
| `sentinel_gap_count`       | <1     | `>=1 → 경고`             |
| `nodecache_resident_bytes` | 안정   | `5e9 5분 초과 → 경고`     |
| `orphan_queue_total`       | 감소   | `3시간 상승 추세 → GC 점검` |
| `compute_nodes_total`      | <50k   | `10분 >50k → 경고`       |
| `queues_total`             | <100k  | `10분 >100k → 경고`      |

이 한계에 근접하기 전에 클러스터 규모를 확장해야 합니다. 예: Neo4j 메모리 증설, Kafka 브로커 추가 등으로 인제스트 처리량을 유지하세요.

---

## 7. 보안 (확장)

* **인증(Authn):** mTLS + JWT 어서션, 키 교체 주기 12시간.
* **인가(Authz):** Neo4j RBAC + Kafka ACL (`READ_TOPIC`, `WRITE_TOPIC`).
* **감사:** 모든 Diff req/res → OpenTelemetry 트레이스 + 해시.

---

## 8. 잠재 취약점 & 완화 (확장)

| 취약점                  | 레벨     | 설명                           | 완화                                       |
| -------------------- | ------ | ---------------------------- | ---------------------------------------- |
| 그래프 팽창           | 보통    | 수천 버전 누적                   | Sentinel TTL/보관, 오프라인 컴팩션          |
| 해시 충돌             | 낮음    | BLAKE3 충돌 가능성 매우 낮음      | BLAKE3 XOF(더 긴 다이제스트) + 도메인 분리 + 감사 로그 강화 |
| 큐 이름 충돌          | 낮음    | 브로커 소문자 고유성              | `_v{n}` 접미사 추가                         |
| 통계 과다             | 보통    | GetQueueStats 남용               | 레이트 리밋(5/s), 인가 범위 축소              |

---

## 9. Service Level Objectives (SLO)

| SLO ID | 목표                        | 측정             | 윈도우 |
| ------ | -------------------------- | -------------- | ------ |
| SLO‑1  | Diff p95 <100 ms           | Prom 히스토그램 | 28d    |
| SLO‑2  | 큐 생성 성공률 99.9%        | 성공/전체        | 30d    |
| SLO‑3  | Sentinel gap =0            | 게이지           | 90d    |

---

## 10. Testing & Validation

* **Unit:** `pytest plugins` → hash calculation, schema diff edge cases.
* **Integration:** Docker‑Compose (Kafka, Neo4j, Gateway stub) → Diff latency, GC batch.
* **Chaos:** Toxiproxy split‑brain, network delay injection.
* **CI/CD Gate:** SSA DAG Lint와 20종 백테스트 → 24h 카나리아 → 50% 프로모션
  이후 자동 배포, `dagmanager redo-diff --sentinel <id> --rollback`으로 역방향 롤백.

---

## 11. Admin CLI Snippets (예)

```shell
# Diff 예시(비파괴 읽기)
qmtl service dagmanager diff --file dag.json
# 큐 통계 조회
qmtl service dagmanager queue-stats --tag indicator --interval 1h
# 센티널 GC 트리거
qmtl service dagmanager gc --sentinel v1.2.3
# 스키마 DDL 내보내기
qmtl service dagmanager export-schema --out schema.cypher
```

카나리아 배포 단계는 [`docs/canary_rollout.md`](../operations/canary_rollout.md)를 참고하세요.

## 12. 서버 설정 파일 사용법

`qmtl service dagmanager server` 서브커맨드는 YAML 형식의 설정 파일 하나만 받는다.
아래 예시와 같이 모든 서버 옵션을 YAML에 작성하고 필요하다면 ``--config`` 옵션으로 경로를 지정한다.

예시:

```yaml
neo4j_dsn: bolt://db:7687
neo4j_user: neo4j
neo4j_password: secret
kafka_dsn: localhost:9092
```

``qmtl project init``가 설치하는 샘플 파일은 로컬 개발을 위해 인메모리 레포지토리와 큐를 기본값으로 사용합니다. 위 DSN 주석을 해제하면 Neo4j/Kafka 연동이 활성화됩니다.

```
# 기본값으로 실행
qmtl service dagmanager server

# YAML 설정 파일로 실행
qmtl service dagmanager server --config qmtl/examples/qmtl.yml
```

해당 명령은 `qmtl/examples/qmtl.yml` 의 ``dagmanager`` 섹션을 읽어 서버를 실행한다.
``--config`` 옵션을 생략하면 DSN이 제공되지 않으므로 메모리 레포지토리와 큐가
사용된다. 샘플 파일에는 모든 필드를 주석과 함께 설명한다.

사용 가능한 플래그:

- ``--config`` – 구성 파일 경로(선택)

{{ nav_links() }}
