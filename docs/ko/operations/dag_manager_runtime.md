---
title: "DAG Manager 런타임 및 배포 프로필"
tags: [operations, dagmanager, runtime]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# DAG Manager 런타임 및 배포 프로필

## 관련 문서

- [DAG Manager](../architecture/dag-manager.md)
- [백엔드 퀵스타트](backend_quickstart.md)
- [Config CLI](config-cli.md)
- [DAG Manager 컴퓨트 컨텍스트 롤아웃](dagmanager_diff_context_rollout.md)
- [Canary Rollout](canary_rollout.md)

## 목적

이 문서는 DAG Manager의 런타임 요구사항, Neo4j/Kafka/ControlBus 의존성, 기동 전 점검과 장애 대응 포인트를 운영 관점에서 정리한다.

- 그래프 SSOT, diff 계약, queue orchestration의 규범 의미는 [DAG Manager](../architecture/dag-manager.md)에서 다룬다.
- 이 문서는 어떤 인프라가 필수인지와 운영 중 어떤 장애를 우선 확인해야 하는지에 집중한다.

## 런타임 프로필

### `profile: dev`

- `dagmanager.neo4j_dsn`이 비어 있으면 인메모리 그래프 저장소를 허용한다.
- `dagmanager.kafka_dsn`이 비어 있으면 인메모리 큐/토픽 경로를 허용한다.
- `dagmanager.controlbus_dsn` 또는 `dagmanager.controlbus_queue_topic`이 비어 있으면 queue update 발행을 비활성화한다.

### `profile: prod`

- 다음 항목은 fail-fast 대상이다.
  - `dagmanager.neo4j_dsn`
  - `dagmanager.kafka_dsn`
  - `dagmanager.controlbus_dsn`
  - `dagmanager.controlbus_queue_topic`
- `profile: prod`에서는 인메모리 fallback을 운영 모드로 허용하지 않는다.
- `qmtl config validate`에서 warning이 아니라 오류로 막혀야 한다.

## 기동 전 점검

1. `uv run qmtl config validate --config <path> --offline`
2. Neo4j DSN과 인증 정보 확인
3. Kafka/Redpanda bootstrap과 토픽 정책 확인
4. ControlBus queue topic 존재 여부 확인
5. 필요 시 `qmtl --admin dagmanager-server neo4j-init ...` 로 제약/인덱스 적용

## 외부 의존성

- **Neo4j**: global strategy graph SSOT
- **Kafka/Redpanda**: data queue 와 commit-log 경계
- **ControlBus**: `QueueUpdated` 같은 제어 이벤트 fan-out
- **Gateway**: submission ingress와 diff 요청 주체

## 장애 대응 체크리스트

- Neo4j 미도달:
  - prod에서는 기동 실패가 정상이다
  - 제약/인덱스 적용 여부와 리더 상태를 먼저 점검한다
- Kafka/Redpanda 장애:
  - topic orchestration과 queue lifecycle이 멈추므로 queue update 경고를 먼저 확인한다
  - canary나 queue namespace 전환 중이었다면 [Canary Rollout](canary_rollout.md) 절차를 같이 본다
- ControlBus 비활성:
  - queue update fan-out이 빠진 상태로 뜬 것인지 확인한다
  - 브로커와 topic 설정은 [ControlBus/큐 운영 표준](controlbus_queue_standards.md)과 함께 점검한다
- in-memory fallback 오동작:
  - dev 설정이 의도치 않게 prod 배포에 유입되지 않았는지 확인한다

## 관측 포인트

- health/status 및 diff 관련 메트릭은 [모니터링 및 알림](monitoring.md)에서 본다.
- compute context rollout과 diff 전환 이슈는 [DAG Manager 컴퓨트 컨텍스트 롤아웃](dagmanager_diff_context_rollout.md)과 함께 본다.
- graph snapshot/freeze 절차는 [DAG 스냅샷 및 프리즈](dag_snapshot.md)에서 본다.

{{ nav_links() }}
