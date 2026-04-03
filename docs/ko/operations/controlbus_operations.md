---
title: "ControlBus 운영 프로필 및 장애 대응"
tags: [operations, controlbus, queue]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# ControlBus 운영 프로필 및 장애 대응

## 관련 문서

- [ControlBus](../architecture/controlbus.md)
- [ControlBus/큐 운영 표준](controlbus_queue_standards.md)
- [월드 활성화 런북](activation.md)
- [ACK/Gap Resync RFC (초안)](../design/ack_resync_rfc.md)

## 목적

이 문서는 ControlBus의 브로커/토픽 요구사항, dev/prod 운영 차이, lag/gap/ACK 관련 장애 대응 포인트를 운영 관점에서 정리한다.

- 이벤트 의미론과 envelope 스키마는 [ControlBus](../architecture/controlbus.md)에서 다룬다.
- 이 문서는 브로커가 비거나 lag가 커질 때 어떤 증상이 나타나고 무엇을 먼저 점검해야 하는지에 집중한다.

## 런타임 프로필

### `profile: dev`

- ControlBus를 끈 채 로컬 실행할 수 있다.
- 이 경우 publisher/consumer는 경고를 남기고 I/O를 건너뛴다.
- activation/policy/queue 업데이트는 생성되더라도 downstream fan-out이 일어나지 않을 수 있다.

### `profile: prod`

- ControlBus는 필수다.
- 브로커/토픽이 없거나 Kafka 클라이언트를 사용할 수 없으면 Gateway, WorldService, DAG Manager가 fail-fast 해야 한다.
- 토픽 네임스페이스, retention, consumer group 표준은 [ControlBus/큐 운영 표준](controlbus_queue_standards.md)을 따른다.

## 운영 체크리스트

- 토픽 존재 여부
  - `activation`
  - `control.activation.ack`
  - `queue`
  - `policy`
  - `sentinel_weight`
- 소비자 그룹 상태
  - Gateway relay consumer
  - WorldService risk-hub/control consumers
  - 필요한 재시도/DLQ 정책
- ACK/gap 타임아웃
  - `activation_gap_timeout_ms`
  - stale relay 경보

## 장애 대응 체크리스트

- 브로커 장애:
  - prod에서는 degraded operation이 아니라 incident로 취급한다
  - Gateway/WorldService/DAG Manager의 fail-fast 여부와 재기동 루프를 먼저 확인한다
- lag 증가:
  - consumer group lag, dropped subscriber, event fan-out 지표를 함께 본다
  - world activation stale 징후가 있으면 [월드 활성화 런북](activation.md)도 같이 본다
- ACK gap 또는 out-of-order:
  - `requires_ack=true` 이벤트의 sequence 버퍼링, 강제 재정렬, dropped gap 이벤트를 확인한다
  - 운영 기준은 [ACK/Gap Resync RFC (초안)](../design/ack_resync_rfc.md)와 함께 해석한다
- duplicate/replay:
  - `etag`/`run_id`/`idempotency_key` 기반 dedupe가 동작하는지 확인한다

## 관측 포인트

- 메트릭과 rehearsal 시나리오는 [ControlBus/큐 운영 표준](controlbus_queue_standards.md)에 따른다.
- activation apply 경로는 [월드 활성화 런북](activation.md)과 같이 봐야 한다.
- 전역 모니터링/알림 라우팅은 [모니터링 및 알림](monitoring.md)에서 관리한다.

{{ nav_links() }}
